"""Graphe LangGraph multi-agents pour répondre aux questions sur le club.

                         ┌──► historian ────┐
  start_turn ─► supervisor ──► task_manager ──┼──► synthesizer ─► fin
                         └──► analyst ──────┘
                 (un ou plusieurs agents, en parallèle)

- supervisor   : lit la question (et l'historique) et choisit les agents utiles (sortie JSON validée).
- historian    : agent RAG. Reformule la question si besoin, cherche les passages via l'outil MCP
                 `search_meetings`, puis répond en citant ses sources [1], [2]...
- task_manager : agent ReAct (boucle LLM ⇄ outils) avec des outils MCP en liste blanche : il peut
                 lire ET modifier les tâches (« marque la tâche de Karim comme terminée »).
- analyst      : lit `get_stats` et les retards via MCP, puis fait le bilan chiffré.
- synthesizer  : fusionne les rapports en une seule réponse (aucun appel LLM s'il n'y en a qu'un).

La conversation est mémorisée par thread_id grâce au checkpointer LangGraph (SQLite).
"""
from datetime import date
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from ..config import MAX_AGENT_STEPS, TOP_K
from ..schemas import Route
from ..services.llm import LANGUAGE_NAMES, ainvoke_json, ainvoke_text, get_chat_model
from . import prompts

AGENTS = ("historian", "task_manager", "analyst")
AGENT_LABELS = {"supervisor": "Superviseur", "historian": "Archiviste (RAG)", "task_manager": "Gestionnaire des tâches",
                "analyst": "Analyste", "synthesizer": "Synthèse"}
# Outils MCP confiés à l'agent des tâches : pas de suppression ni d'outil d'ingestion
TASK_TOOLS = ["list_tasks", "create_task", "update_task", "list_members", "list_meetings", "get_meeting"]


def per_turn(current, update):
    """Réducteur : None remet la liste à zéro (début d'un tour), sinon on ajoute."""
    if update is None:
        return []
    return (current or []) + update


class ChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    language: str
    route: list[str]
    reports: Annotated[list[dict], per_turn]
    sources: Annotated[list[dict], per_turn]
    trace: Annotated[list[dict], per_turn]


def last_question(state):
    for message in reversed(state["messages"]):
        if isinstance(message, HumanMessage):
            return message.content
    return ""


def history_text(state, limit=6):
    lines = []
    for message in state["messages"][:-1][-limit:]:
        role = "Utilisateur" if isinstance(message, HumanMessage) else "Assistant"
        lines.append(f"{role} : {message.content[:500]}")
    return "\n".join(lines) or "(aucun)"


def heuristic_route(question):
    """Routage de secours, si le LLM superviseur échoue."""
    q = question.lower()
    agents = []
    if any(w in q for w in ("décid", "decid", "dit", "réunion", "reunion", "pourquoi", "budget", "meeting")):
        agents.append("historian")
    if any(w in q for w in ("tâche", "tache", "task", "qui doit", "termin", "échéance", "assign", "marque")):
        agents.append("task_manager")
    if any(w in q for w in ("bilan", "avancement", "retard", "stat", "charge", "priorit", "overdue", "progress")):
        agents.append("analyst")
    return agents or ["historian"]


def build_task_agent(tools):
    """Sous-graphe ReAct : le LLM appelle les outils MCP jusqu'à pouvoir répondre."""
    tool_node = ToolNode(tools, handle_tool_errors=True)

    async def call_model(state: MessagesState):
        model = get_chat_model().bind_tools(tools)
        return {"messages": [await model.ainvoke(state["messages"])]}

    graph = StateGraph(MessagesState)
    graph.add_node("model", call_model)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", tools_condition)
    graph.add_edge("tools", "model")
    return graph.compile()


def build_chat_graph(mcp, task_tools, checkpointer=None):
    task_agent = build_task_agent(task_tools) if task_tools else None

    def lang(state):
        return LANGUAGE_NAMES.get(state.get("language", "fr"), "français")

    def start_turn(_: ChatState):
        return {"reports": None, "sources": None, "trace": None, "route": []}

    async def supervisor(state: ChatState):
        question = last_question(state)
        try:
            route = await ainvoke_json(
                [HumanMessage(prompts.SUPERVISOR.format(history=history_text(state), question=question))],
                Route, role="router")
            agents, reasoning = route.agents, route.reasoning
        except Exception as error:  # noqa: BLE001 - un routage raté ne doit pas bloquer la réponse
            agents, reasoning = heuristic_route(question), f"routage de secours ({type(error).__name__})"
        if not task_agent:
            agents = [a for a in agents if a != "task_manager"]
        return {"route": agents, "trace": [{"agent": "supervisor", "detail": reasoning, "agents": agents}]}

    def dispatch(state: ChatState):
        return state["route"] or ["synthesizer"]

    async def historian(state: ChatState):
        question = last_question(state)
        if len(state["messages"]) > 1:
            question = await ainvoke_text(
                [HumanMessage(prompts.CONDENSE.format(history=history_text(state), question=question))], role="router")
        passages = await mcp.call("search_meetings", {"query": question, "k": TOP_K})
        trace = {"agent": "historian", "detail": f"search_meetings → {len(passages)} passage(s)",
                 "tools": [{"name": "search_meetings", "args": {"query": question}}]}
        if not passages:
            return {"reports": [{"agent": "historian", "content": "Aucun compte-rendu n'est encore indexé."}],
                    "trace": [trace]}
        context = "\n\n".join(
            f"[{i}] (Réunion « {p['title']} » du {p['date']}, {p['label']})\n{p['text']}"
            for i, p in enumerate(passages, start=1))
        answer = await ainvoke_text([HumanMessage(prompts.HISTORIAN.format(
            lang=lang(state), context=context, question=question))])
        sources = [{"number": i, "title": p["title"], "date": p["date"], "label": p["label"],
                    "meeting_id": p["meeting_id"], "score": p.get("score"), "excerpt": p["text"][:300]}
                   for i, p in enumerate(passages, start=1)]
        return {"reports": [{"agent": "historian", "content": answer}], "sources": sources, "trace": [trace]}

    async def task_manager(state: ChatState):
        system = SystemMessage(prompts.TASK_MANAGER.format(today=date.today().isoformat(), lang=lang(state)))
        history = [m for m in state["messages"][-7:] if isinstance(m, (HumanMessage, AIMessage)) and m.content]
        result = await task_agent.ainvoke({"messages": [system, *history]},
                                          {"recursion_limit": 2 * MAX_AGENT_STEPS + 1})
        new_messages = result["messages"][len(history) + 1:]
        calls = [{"name": c["name"], "args": c["args"]}
                 for m in new_messages if isinstance(m, AIMessage) for c in (m.tool_calls or [])]
        answer = result["messages"][-1].content
        return {"reports": [{"agent": "task_manager", "content": answer}],
                "trace": [{"agent": "task_manager", "detail": f"{len(calls)} appel(s) d'outil MCP", "tools": calls}]}

    async def analyst(state: ChatState):
        stats = await mcp.call("get_stats")
        overdue = await mcp.call("list_tasks", {"overdue_only": True})
        stats_text = (f"{stats['meetings']} réunions, {stats['tasks_total']} tâches : {stats['tasks_todo']} à faire, "
                      f"{stats['tasks_in_progress']} en cours, {stats['tasks_done']} terminées, "
                      f"{stats['tasks_overdue']} en retard.\nPar membre : " + "; ".join(
                          f"{m['name']} ({m['done']}/{m['total']} terminées, {m['overdue']} en retard)"
                          for m in stats["members"]))
        overdue_text = "\n".join(f"- {t['description']} | {t['assignee']} | échéance {t['due_date']}"
                                 for t in overdue) or "Aucune."
        answer = await ainvoke_text([HumanMessage(prompts.ANALYST.format(
            today=date.today().isoformat(), lang=lang(state), stats=stats_text, overdue=overdue_text,
            question=last_question(state)))])
        return {"reports": [{"agent": "analyst", "content": answer}],
                "trace": [{"agent": "analyst", "detail": "get_stats + list_tasks(overdue_only)",
                           "tools": [{"name": "get_stats", "args": {}},
                                     {"name": "list_tasks", "args": {"overdue_only": True}}]}]}

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
        detail = "réponse directe" if len(reports) == 1 else f"fusion de {len(reports)} rapport(s)"
        return {"messages": [AIMessage(answer)], "trace": [{"agent": "synthesizer", "detail": detail}]}

    graph = StateGraph(ChatState)
    graph.add_node("start_turn", start_turn)
    graph.add_node("supervisor", supervisor)
    graph.add_node("historian", historian)
    graph.add_node("analyst", analyst)
    if task_agent:
        graph.add_node("task_manager", task_manager)
    graph.add_node("synthesizer", synthesizer)

    targets = [a for a in AGENTS if a != "task_manager" or task_agent] + ["synthesizer"]
    graph.add_edge(START, "start_turn")
    graph.add_edge("start_turn", "supervisor")
    graph.add_conditional_edges("supervisor", dispatch, targets)
    for agent in targets[:-1]:
        graph.add_edge(agent, "synthesizer")
    graph.add_edge("synthesizer", END)
    return graph.compile(checkpointer=checkpointer)


async def ask(graph, question, language="fr", thread_id="default"):
    result = await graph.ainvoke(
        {"messages": [HumanMessage(question)], "language": language},
        {"configurable": {"thread_id": thread_id}},
    )
    trace = [{**step, "label": AGENT_LABELS.get(step["agent"], step["agent"])} for step in result.get("trace", [])]
    return {
        "answer": result["messages"][-1].content,
        "sources": result.get("sources", []),
        "agents": result.get("route", []),
        "trace": trace,
        "thread_id": thread_id,
    }
