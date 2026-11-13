"""Graphe LangGraph d'ingestion d'un cours.

                      ┌──────────► index ────────────────────────────┐
  load ─► structure ──┤                                              ├──► persist ─► link (agent linker)
                      └──► analyze_chapter ×N ─► synthesize ─────────┘
                           (en parallèle)

- load            : texte collé, PDF, TXT, ou audio transcrit par Whisper.
- structure       : découpe le cours en chapitres (titres détectés, sinon par taille).
- index           : indexe les morceaux dans ChromaDB via MCP (RAG), en parallèle de l'analyse.
- analyze_chapter : une instance par chapitre (API Send) : titre, résumé, notions, compétences à acquérir
                    et prérequis, en JSON validé par Pydantic, avec nouvelles tentatives (RetryPolicy).
- synthesize      : résumé du cours, notions clés et quiz, à partir des résumés des chapitres.
- persist         : jointure (index + synthesize) ; enregistre le cours et construit le graphe de connaissances.
- link            : l'agent linker relie chaque chapitre aux chapitres PRÉCÉDENTS qui enseignent ses prérequis.
"""
import asyncio
import operator
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from ..config import MAX_CHARS_PER_CHAPTER
from ..schemas import ChapterAnalysis, CourseMaterial
from ..services import documents, transcription
from ..services.llm import LANGUAGE_NAMES, LLMNotConfigured, ainvoke_json
from . import prompts
from .linker import link_course

LLM_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, retry_on=lambda e: not isinstance(e, LLMNotConfigured))


class IngestState(TypedDict, total=False):
    course_id: int
    title: str
    language: str
    source_type: str
    text: str | None
    file_path: str | None
    sections: list[dict]
    full_text: str
    chapters: list[dict]
    analyses: Annotated[list[dict], operator.add]
    indexed: int
    material: dict
    saved_chapters: list[dict]
    links: list[dict]
    warnings: Annotated[list[str], operator.add]


class ChapterState(TypedDict):
    index: int
    total: int
    course_title: str
    language: str
    chapter: dict


def lang_name(code):
    return LANGUAGE_NAMES.get(code, "français")


def build_ingestion_graph(mcp):
    async def load(state: IngestState):
        if state["source_type"] == "saisie":
            sections = [{"label": "texte", "text": (state.get("text") or "").strip()}]
        else:
            path = Path(state["file_path"])
            readers = {"audio": lambda p: transcription.transcribe_audio(p, state["language"]),
                       "pdf": documents.read_pdf, "texte": documents.read_text_file}
            sections = await asyncio.to_thread(readers[state["source_type"]], path)
        sections = [s for s in sections if s["text"].strip()]
        if not sections:
            raise ValueError("Aucun texte n'a pu être extrait.")
        return {"sections": sections}

    def structure(state: IngestState):
        chapters = documents.split_into_chapters(state["sections"])
        warnings = [f"Chapitre « {c['title'] or i + 1} » tronqué à {MAX_CHARS_PER_CHAPTER} caractères pour l'analyse."
                    for i, c in enumerate(chapters) if len(c["text"]) > MAX_CHARS_PER_CHAPTER]
        return {"full_text": "\n\n".join(s["text"] for s in state["sections"]), "chapters": chapters,
                "warnings": warnings}

    def fan_out(state: IngestState):
        total = len(state["chapters"])
        return [Send("index", state)] + [
            Send("analyze_chapter", {"index": i, "total": total, "course_title": state["title"],
                                     "language": state["language"], "chapter": chapter})
            for i, chapter in enumerate(state["chapters"])]

    async def index(state: IngestState):
        chunks = documents.split_into_chunks(state["sections"])
        result = await mcp.call("index_course", {"course_id": state["course_id"], "chunks": chunks})
        return {"indexed": result["indexed"]}

    async def analyze_chapter(state: ChapterState):
        chapter = state["chapter"]
        hint = f", intitulé « {chapter['title']} »" if chapter["title"] else ""
        analysis = await ainvoke_json([HumanMessage(prompts.CHAPTER_ANALYSIS.format(
            index=state["index"] + 1, total=state["total"], course_title=state["course_title"], title_hint=hint,
            lang=lang_name(state["language"]), text=chapter["text"][:MAX_CHARS_PER_CHAPTER]))], ChapterAnalysis)
        data = analysis.model_dump()
        # Le titre détecté dans le document a priorité ; sinon celui proposé par le LLM
        data["title"] = chapter["title"] or data["title"] or f"Partie {state['index'] + 1}"
        taught = {c["name"].lower() for c in data["concepts"]}
        data["prerequisites"] = [p for p in data["prerequisites"] if p.lower() not in taught]
        return {"analyses": [{"index": state["index"], "label": chapter["label"], **data}]}

    async def synthesize(state: IngestState):
        analyses = sorted(state["analyses"], key=lambda a: a["index"])
        text = "\n\n".join(f"{a['index'] + 1}. {a['title']}\n{a['summary']}\nNotions : "
                           + ", ".join(c["name"] for c in a["concepts"]) for a in analyses)
        material = await ainvoke_json([HumanMessage(prompts.COURSE_MATERIAL.format(
            course_title=state["title"], lang=lang_name(state["language"]), chapters=text,
            quiz_size=5 if len(analyses) < 4 else 8))], CourseMaterial)
        return {"material": material.model_dump()}

    async def persist(state: IngestState):
        analyses = sorted(state["analyses"], key=lambda a: a["index"])
        material = state["material"]
        saved = await mcp.call("save_course_analysis", {
            "course_id": state["course_id"], "content": state["full_text"], "summary": material["summary"],
            "key_concepts": material["key_concepts"], "quiz": material["quiz"],
            "chapters": [{k: a[k] for k in ("title", "summary", "label", "concepts", "skills", "prerequisites")}
                         for a in analyses]})
        return {"saved_chapters": saved["chapters"]}

    async def link(state: IngestState):
        result = await link_course(mcp, state["course_id"], state["language"])
        return {"links": result["links"]}

    graph = StateGraph(IngestState)
    graph.add_node("load", load)
    graph.add_node("structure", structure)
    graph.add_node("index", index, retry_policy=RetryPolicy(max_attempts=2))
    graph.add_node("analyze_chapter", analyze_chapter, retry_policy=LLM_RETRY)
    graph.add_node("synthesize", synthesize, retry_policy=LLM_RETRY)
    graph.add_node("persist", persist)
    graph.add_node("link", link)

    graph.add_edge(START, "load")
    graph.add_edge("load", "structure")
    graph.add_conditional_edges("structure", fan_out, ["index", "analyze_chapter"])
    graph.add_edge("analyze_chapter", "synthesize")
    graph.add_edge(["index", "synthesize"], "persist")
    graph.add_edge("persist", "link")
    graph.add_edge("link", END)
    return graph.compile()


async def process_course(mcp, course_id, title, language, source_type, text=None, file_path=None):
    """Exécute le graphe ; en cas d'échec, le cours passe en statut « error » avec le message."""
    try:
        return await build_ingestion_graph(mcp).ainvoke({
            "course_id": course_id, "title": title, "language": language, "source_type": source_type,
            "text": text, "file_path": file_path, "analyses": [], "warnings": []})
    except Exception as error:  # noqa: BLE001
        await mcp.call("fail_course", {"course_id": course_id, "error": str(error) or type(error).__name__})
        return None
    finally:
        if file_path:
            Path(file_path).unlink(missing_ok=True)
