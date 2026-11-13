import pytest
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agents.chat import ask, build_chat_graph, heuristic_route

from .conftest import FakeMCP

PASSAGE = {"text": "Le budget de 300 euros est validé.", "title": "Bureau", "date": "2026-11-01",
           "label": "page 1", "meeting_id": 1, "score": 0.8}
STATS = {"meetings": 1, "tasks_total": 2, "tasks_todo": 1, "tasks_in_progress": 0, "tasks_done": 1,
         "tasks_overdue": 1, "members": [{"name": "Karim", "total": 2, "done": 1, "overdue": 1}], "upcoming": []}


@tool
def list_tasks(assignee: str = "") -> str:
    """Liste les tâches."""
    return '[{"id": 4, "description": "Affiche", "assignee": "Karim"}]'


@pytest.fixture
def graph(fake_llm):
    mcp = FakeMCP({"search_meetings": [PASSAGE], "get_stats": STATS, "list_tasks": []})
    return build_chat_graph(mcp, [list_tasks], InMemorySaver()), mcp


async def test_historian_answers_with_sources(graph):
    chat_graph, mcp = graph
    result = await ask(chat_graph, "Qu'a-t-on décidé pour le budget ?", thread_id="t1")
    assert result["agents"] == ["historian"]
    assert result["answer"] == "Le budget de 300 euros a été validé [1]."
    assert result["sources"][0]["title"] == "Bureau"
    assert [s["agent"] for s in result["trace"]] == ["supervisor", "historian", "synthesizer"]


async def test_task_manager_uses_mcp_tools(graph):
    chat_graph, _ = graph
    result = await ask(chat_graph, "Quelles sont les tâches de Karim ?", thread_id="t2")
    assert result["agents"] == ["task_manager"]
    assert "Affiche" in result["answer"]
    step = next(s for s in result["trace"] if s["agent"] == "task_manager")
    assert step["tools"] == [{"name": "list_tasks", "args": {"assignee": "Karim"}}]


async def test_several_agents_run_in_parallel_then_synthesize(graph):
    chat_graph, mcp = graph
    result = await ask(chat_graph, "Fais le bilan et dis-moi ce qu'on a décidé", thread_id="t3")
    assert set(result["agents"]) == {"historian", "analyst"}
    assert result["answer"] == "Synthèse finale [1]."
    assert {"search_meetings", "get_stats"} <= set(mcp.names())


async def test_memory_keeps_thread_and_resets_turn_state(graph):
    chat_graph, _ = graph
    await ask(chat_graph, "Qu'a-t-on décidé ?", thread_id="t4")
    second = await ask(chat_graph, "Bonjour", thread_id="t4")
    assert second["agents"] == [] and second["sources"] == []  # rien ne déborde du tour précédent
    state = await chat_graph.aget_state({"configurable": {"thread_id": "t4"}})
    assert len(state.values["messages"]) == 4  # 2 questions + 2 réponses mémorisées


async def test_follow_up_question_is_condensed(graph, fake_llm):
    chat_graph, mcp = graph
    await ask(chat_graph, "Qu'a-t-on décidé ?", thread_id="t5")
    await ask(chat_graph, "Et qu'a-t-on décidé ensuite ?", thread_id="t5")
    queries = [args["query"] for name, args in mcp.calls if name == "search_meetings"]
    assert queries[-1] == "Question reformulée"


def test_heuristic_route_fallback():
    assert heuristic_route("Quelles tâches sont en retard ?") == ["task_manager", "analyst"]
    assert heuristic_route("blabla") == ["historian"]
