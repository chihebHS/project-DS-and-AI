"""Graphes LangGraph (ingestion, linker, chat) avec un faux LLM et un faux client MCP."""
import pytest
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

from app.agents import ingestion
from app.agents.chat import ask, build_chat_graph, heuristic_route
from app.agents.linker import link_course

from .conftest import FakeMCP

COURSE_TEXT = ("Chapitre 1 : Modèle relationnel\n" + "Les tables et la clé primaire. " * 5
               + "\nChapitre 2 : Requêtes SELECT\n" + "La requête select et les jointures. " * 5)


def ingestion_mcp():
    return FakeMCP({
        "index_course": lambda a: {"indexed": len(a["chunks"])},
        "save_course_analysis": lambda a: {"chapters": [{"id": 10 + i, "position": i + 1, "title": c["title"]}
                                                        for i, c in enumerate(a["chapters"])]},
        "list_chapters": [], "fail_course": {"status": "error"}})


async def test_ingestion_builds_chapters_and_material(fake_llm):
    mcp = ingestion_mcp()
    result = await ingestion.process_course(mcp, 1, "Bases de données", "fr", "saisie", text=COURSE_TEXT)
    names = mcp.names()
    assert names.index("save_course_analysis") > names.index("index_course")  # jointure
    saved = dict(mcp.calls)["save_course_analysis"]
    chapters = saved["chapters"]
    assert [c["title"] for c in chapters] == ["Chapitre 1 : Modèle relationnel", "Chapitre 2 : Requêtes SELECT"]
    assert chapters[1]["prerequisites"] == ["Clé primaire", "Table"]
    assert chapters[1]["skills"] == ["Écrire une requête SQL"]
    assert saved["quiz"][0]["answer_index"] == 0
    assert "list_chapters" in names  # l'agent linker a tourné
    assert result["saved_chapters"][0]["id"] == 10


async def test_untitled_parts_get_llm_titles(fake_llm, monkeypatch):
    monkeypatch.setattr(ingestion.documents, "split_into_chapters",
                        lambda s: [{"title": "", "text": "modèle relationnel", "label": "texte"},
                                   {"title": "", "text": "requête select", "label": "texte"}])
    mcp = ingestion_mcp()
    await ingestion.process_course(mcp, 1, "BD", "fr", "saisie", text="x")
    assert [c["title"] for c in dict(mcp.calls)["save_course_analysis"]["chapters"]] == ["Titre LLM 1", "Titre LLM 2"]


async def test_ingestion_failure_marks_course(fake_llm):
    mcp = ingestion_mcp()
    assert await ingestion.process_course(mcp, 3, "Vide", "fr", "saisie", text="  ") is None
    assert mcp.calls[-1] == ("fail_course", {"course_id": 3, "error": "Aucun texte n'a pu être extrait."})


def linker_mcp():
    chapters = [{"id": 2, "title": "SELECT", "course_title": "BD"}, {"id": 3, "title": "Pandas", "course_title": "Py"}]
    candidates = {
        2: [{"chapter_id": 1, "title": "Relationnel", "course_title": "BD", "best_score": 1.0,
             "matches": [{"prerequisite": "Clé primaire", "concept": "Clé primaire", "score": 1.0, "method": "exact"}]}],
        3: [{"chapter_id": 2, "title": "SELECT", "course_title": "BD", "best_score": 0.7,
             "matches": [{"prerequisite": "Jointure SQL", "concept": "Jointure", "score": 0.7, "method": "semantic"}]}],
    }
    return FakeMCP({"list_chapters": chapters, "find_prerequisite_candidates": lambda a: candidates[a["chapter_id"]],
                    "add_dependency": lambda a: a})


async def test_linker_accepts_exact_and_validates_semantic(fake_llm):
    mcp = linker_mcp()
    result = await link_course(mcp, 5)
    created = [(a["chapter_id"], a["prerequisite_chapter_id"]) for n, a in mcp.calls if n == "add_dependency"]
    assert created == [(2, 1), (3, 2)] and result["method"] == "llm"


async def test_linker_fallback_keeps_only_strong_semantic_links(fake_llm):
    fake_llm.validate_links = False  # le LLM répond n'importe quoi
    mcp = linker_mcp()
    result = await link_course(mcp, 5)
    created = [(a["chapter_id"], a["prerequisite_chapter_id"]) for n, a in mcp.calls if n == "add_dependency"]
    assert created == [(2, 1)] and result["method"] == "score"  # 0.7 < seuil 0.8


PASSAGE = {"text": "La clé primaire identifie une ligne.", "title": "BD", "label": "page 1", "course_id": 1, "score": 0.9}


@tool
def list_chapters(course_id: int = 0) -> str:
    """Liste les chapitres."""
    return '[{"id": 2, "title": "Requêtes SELECT"}]'


@pytest.fixture
def chat(fake_llm):
    mcp = FakeMCP({"search_courses": [PASSAGE]})
    return build_chat_graph(mcp, [list_chapters], InMemorySaver()), mcp


async def test_tutor_answers_with_sources(chat):
    graph, mcp = chat
    result = await ask(graph, "Explique la clé primaire", thread_id="t1", course_id=1)
    assert result["agents"] == ["tutor"] and result["sources"][0]["label"] == "page 1"
    assert dict(mcp.calls)["search_courses"]["course_id"] == 1


async def test_navigator_uses_graph_tools(chat):
    graph, _ = chat
    result = await ask(graph, "Quels sont les prérequis du chapitre SELECT ?", thread_id="t2")
    step = next(s for s in result["trace"] if s["agent"] == "navigator")
    assert step["tools"] == [{"name": "list_chapters", "args": {}}] and "Requêtes SELECT" in result["answer"]


async def test_quizmaster_returns_structured_quiz(chat):
    graph, _ = chat
    result = await ask(graph, "Fais-moi un quiz", thread_id="t3")
    assert result["agents"] == ["quizmaster"] and len(result["quiz"]) == 3


async def test_parallel_agents_and_memory_reset(chat):
    graph, _ = chat
    both = await ask(graph, "Explique les jointures et donne les prérequis", thread_id="t4")
    assert set(both["agents"]) == {"tutor", "navigator"} and both["answer"] == "Synthèse finale [1]."
    hello = await ask(graph, "Bonjour", thread_id="t4")
    assert hello["agents"] == [] and hello["sources"] == [] and hello["quiz"] == []
    state = await graph.aget_state({"configurable": {"thread_id": "t4"}})
    assert len(state.values["messages"]) == 4


def test_heuristic_route():
    assert heuristic_route("Par quoi commencer avant ce chapitre ?") == ["navigator"]
    assert heuristic_route("Fais un QCM") == ["quizmaster"]
    assert heuristic_route("Qu'est-ce qu'un index ?") == ["tutor"]
