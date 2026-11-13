"""Graphe LangGraph multi-agents pour réviser.

                         ┌──► tutor ───────┐
  start_turn ─► supervisor ──► navigator ───┼──► synthesizer ─► fin
                         └──► quizmaster ──┘
                 (un ou plusieurs agents, en parallèle)

- supervisor : choisit les agents utiles (sortie JSON validée, routage par mots-clés en secours).
- tutor      : agent RAG. Reformule la question si besoin, cherche via l'outil MCP `search_courses`,
               explique en citant ses sources [1], [2]...
- navigator  : agent ReAct sur le GRAPHE DE CONNAISSANCES (outils MCP : chapitres, prérequis,
               compétences, parcours de révision, où une notion est enseignée).
- quizmaster : cherche les passages utiles puis génère un quiz d'entraînement (rendu interactif).
- synthesizer: fusionne les rapports (aucun appel LLM s'il n'y en a qu'un).

La conversation est mémorisée par thread_id (checkpointer LangGraph).
"""
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from ..config import MAX_AGENT_STEPS, TOP_K
from ..schemas import Quiz, Route
from ..services.llm import LANGUAGE_NAMES, ainvoke_json, ainvoke_text, get_chat_model
from . import prompts

AGENTS = ("tutor", "navigator", "quizmaster")
AGENT_LABELS = {"supervisor": "Superviseur", "tutor": "Tuteur (RAG)", "navigator": "Navigateur (graphe)",
                "quizmaster": "Examinateur", "synthesizer": "Synthèse"}
# Outils MCP confiés au navigateur : lecture seule du graphe
NAVIGATOR_TOOLS = ["list_courses", "list_chapters", "get_chapter", "learning_path", "find_concept", "graph_stats"]


def per_turn(current, update):
    """Réducteur : None remet la liste à zéro (début d'un tour), sinon on ajoute."""
    if update is None:
        return []
    return (current or []) + update


class ChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    language: str
    course_id: int | None
    route: list[str]
    reports: Annotated[list[dict], per_turn]
    sources: Annotated[list[dict], per_turn]
    quiz: Annotated[list[dict], per_turn]
    trace: Annotated[list[dict], per_turn]


def last_question(state):
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    return ""


def history_text(state, limit=6):
    lines = []
    for message in state["messages"][:-1][-limit:]:
        role = "Étudiant" if isinstance(message, HumanMessage) else "Assistant"
        lines.append(f"{role} : {message.content[:500]}")
    return "\n".join(lines) or "(aucun)"


def heuristic_route(question):
    """Routage de secours, si le LLM superviseur échoue."""
    q = question.lower()
    agents = []
    if any(w in q for w in ("prérequis", "prerequis", "commencer", "chapitre", "compétence", "competence",
                            "parcours", "avant", "ordre", "lien", "prerequisite", "skill")):
        agents.append("navigator")
    if any(w in q for w in ("quiz", "qcm", "interroge", "entraîn", "entrain", "exercice", "teste-moi")):
        agents.append("quizmaster")
    return agents or ["tutor"]


def build_navigator(tools):
    """Sous-graphe ReAct : le LLM interroge le graphe de connaissances via les outils MCP."""
    async def call_model(state: MessagesState):
        model = get_chat_model().bind_tools(tools)
        return {"messages": [await model.ainvoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", ToolNode(tools, handle_tool_errors=True))
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition)
    graph.add_edge("tools", "model")
    return graph.compile()


def build_chat_graph(mcp, navigator_tools, checkpointer=None):
    navigator_agent = build_navigator(navigator_tools) if navigator_tools else None

    def lang(state):
        return LANGUAGE_NAMES.get(state.get("language", "fr"), "français")

    async def standalone_question(state):
        question = last_question(state)
        if len(state["messages"]) > 1:
            question = await ainvoke_text([HumanMessage(prompts.CONDENSE.format(
                history=history_text(state), question=question))], role="router")
        return question

    async def retrieve(state, question):
        args = {"query": question, "k": TOP_K}
        if state.get("course_id"):
            args["course_id"] = state["course_id"]
        return await mcp.call("search_courses", args), args

    def context_of(passages):
        return "\n\n".join(f"[{i}] ({p['title']}, {p['label']})\n{p['text']}" for i, p in enumerate(passages, 1))

    def start_turn(_: ChatState):
        return {"reports": None, "sources": None, "quiz": None, "trace": None, "route": []}

    async def supervisor(state: ChatState):
        question = last_question(state)
        try:
            route = await ainvoke_json([HumanMessage(prompts.SUPERVISOR.format(
                history=history_text(state), question=question))], Route, role="router")
            agents, reasoning = route.agents, route.reasoning
        except Exception as error:  # noqa: BLE001 - un routage raté ne doit pas bloquer la réponse
            agents, reasoning = heuristic_route(question), f"routage de secours ({type(error).__name__})"
        if not navigator_agent:
            agents = [a for a in agents if a != "navigator"]
        return {"route": agents, "trace": [{"agent": "supervisor", "detail": reasoning, "agents": agents}]}

    def dispatch(state: ChatState):
        return state["route"] or ["synthesizer"]

    async def tutor(state: ChatState):
        question = await standalone_question(state)
        passages, args = await retrieve(state, question)
        trace = {"agent": "tutor", "detail": f"search_courses → {len(passages)} passage(s)",
                 "tools": [{"name": "search_courses", "args": args}]}
        if not passages:
            return {"reports": [{"agent": "tutor", "content": "Aucun cours n'est encore importé."}], "trace": [trace]}
        answer = await ainvoke_text([HumanMessage(prompts.TUTOR.format(
            lang=lang(state), context=context_of(passages), question=question))])
        sources = [{"number": i, "title": p["title"], "label": p["label"], "course_id": p["course_id"],
                    "score": p.get("score"), "excerpt": p["text"][:300]} for i, p in enumerate(passages, 1)]
        return {"reports": [{"agent": "tutor", "content": answer}], "sources": sources, "trace": [trace]}

    async def navigator(state: ChatState):
        system = SystemMessage(prompts.NAVIGATOR.format(lang=lang(state)))
        history = [m for m in state["messages"][-7:] if isinstance(m, (HumanMessage, AIMessage)) and m.content]
        result = await navigator_agent.ainvoke({"messages": [system, *history]},
                                               {"recursion_limit": 2 * MAX_AGENT_STEPS + 1})
        new_messages = result["messages"][len(history) + 1:]
        calls = [{"name": c["name"], "args": c["args"]}
                 for m in new_messages if isinstance(m, AIMessage) for c in (m.tool_calls or [])]
        return {"reports": [{"agent": "navigator", "content": result["messages"][-1].content}],
                "trace": [{"agent": "navigator", "detail": f"{len(calls)} appel(s) d'outil MCP", "tools": calls}]}

    async def quizmaster(state: ChatState):
        topic = await standalone_question(state)
        passages, args = await retrieve(state, topic)
        trace = {"agent": "quizmaster", "detail": f"search_courses → {len(passages)} passage(s)",
                 "tools": [{"name": "search_courses", "args": args}]}
        if not passages:
            return {"reports": [{"agent": "quizmaster", "content": "Importe un cours pour pouvoir t'interroger."}],
                    "trace": [trace]}
        quiz = await ainvoke_json([HumanMessage(prompts.QUIZMASTER.format(
            count=3, lang=lang(state), topic=topic, context=context_of(passages)))], Quiz)
        questions = [q.model_dump() for q in quiz.quiz]
        intro = (f"Voici un quiz de {len(questions)} question(s) pour t'entraîner. Réponds dans le quiz ci-dessous."
                 if state.get("language", "fr") == "fr" else
                 f"Here is a {len(questions)}-question quiz to practise. Answer below.")
        return {"reports": [{"agent": "quizmaster", "content": intro}], "quiz": questions, "trace": [trace]}

    async def synthesizer(state: ChatState):
        reports = state.get("reports") or []
        if not reports:
            answer = await ainvoke_text([SystemMessage(prompts.SMALLTALK.format(lang=lang(state))),
                                         HumanMessage(last_question(state))])
        elif len(reports) == 1:
            answer = reports[0]["content"]
        else:
            ordered = sorted(reports, key=lambda r: AGENTS.index(r["agent"]))
            text = "\n\n".join(f"### {AGENT_LABELS[r['agent']]}\n{r['content']}" for r in ordered)
            answer = await ainvoke_text([HumanMessage(prompts.SYNTHESIZER.format(
                lang=lang(state), question=last_question(state), reports=text))])
        detail = "réponse directe" if len(reports) <= 1 else f"fusion de {len(reports)} rapport(s)"
        return {"messages": [AIMessage(answer)], "trace": [{"agent": "synthesizer", "detail": detail}]}

    graph = StateGraph(ChatState)
    graph.add_node("start_turn", start_turn)
    graph.add_node("supervisor", supervisor)
    graph.add_node("tutor", tutor)
    graph.add_node("quizmaster", quizmaster)
    if navigator_agent:
        graph.add_node("navigator", navigator)
    graph.add_node("synthesizer", synthesizer)

    targets = [a for a in AGENTS if a != "navigator" or navigator_agent] + ["synthesizer"]
    graph.add_edge(START, "start_turn")
    graph.add_edge("start_turn", "supervisor")
    graph.add_conditional_edges("supervisor", dispatch, targets)
    for agent in targets[:-1]:
        graph.add_edge(agent, "synthesizer")
    graph.add_edge("synthesizer", END)
    return graph.compile(checkpointer=checkpointer)


async def ask(graph, question, language="fr", thread_id="default", course_id=None):
    result = await graph.ainvoke(
        {"messages": [HumanMessage(question)], "language": language, "course_id": course_id},
        {"configurable": {"thread_id": thread_id}},
    )
    trace = [{**step, "label": AGENT_LABELS.get(step["agent"], step["agent"])} for step in result.get("trace", [])]
    return {"answer": result["messages"][-1].content, "sources": result.get("sources", []),
            "quiz": result.get("quiz", []), "agents": result.get("route", []), "trace": trace,
            "thread_id": thread_id}
