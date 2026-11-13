"""Graphe LangGraph d'ingestion d'un compte-rendu.

                    ┌──────────► index ───────────────────────────────┐
  load ─► prepare ──┤                                                 ├──► persist
                    └──► extract_part ×N ─► merge ─► normalize ───────┘
                         (en parallèle)

- load         : récupère le texte (saisie, PDF, TXT ou audio transcrit par Whisper).
- prepare      : découpe le texte en parties de taille raisonnable pour le LLM.
- index        : indexe les morceaux dans ChromaDB via l'outil MCP `index_meeting` (RAG),
                 en parallèle de l'extraction.
- extract_part : une instance par partie (API Send = map), extraction JSON validée par Pydantic,
                 retentée automatiquement (RetryPolicy) si le LLM renvoie un JSON invalide.
- merge        : fusionne les résultats partiels (reduce) ; un seul appel LLM si plusieurs parties.
- normalize    : nettoie les dates, supprime les tâches vides et les doublons.
- persist      : attend `index` ET `normalize`, puis enregistre tout via l'outil MCP `complete_meeting`.
"""
import asyncio
import operator
from datetime import date
from pathlib import Path
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy, Send

from ..schemas import MeetingExtraction, MergedSummary
from ..services import documents, transcription
from ..services.llm import LANGUAGE_NAMES, LLMNotConfigured, ainvoke_json
from . import prompts

WEEKDAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
LLM_RETRY = RetryPolicy(max_attempts=3, initial_interval=1.0, retry_on=lambda e: not isinstance(e, LLMNotConfigured))


class IngestState(TypedDict, total=False):
    meeting_id: int
    title: str
    meeting_date: str
    language: str
    source_type: str
    text: str | None  # compte-rendu collé
    file_path: str | None  # fichier importé (temporaire)
    sections: list[dict]
    full_text: str
    parts: list[str]
    partials: Annotated[list[dict], operator.add]
    indexed: int
    summary: str
    decisions: list[str]
    tasks: list[dict]
    warnings: Annotated[list[str], operator.add]


class PartState(TypedDict):
    part: str
    index: int
    total: int
    meeting_date: str
    language: str


def build_ingestion_graph(mcp):
    async def load(state: IngestState):
        source = state["source_type"]
        if source == "saisie":
            sections = [{"label": "compte-rendu", "text": (state.get("text") or "").strip()}]
        else:
            path = Path(state["file_path"])
            readers = {"audio": lambda p: transcription.transcribe_audio(p, state["language"]),
                       "pdf": documents.read_pdf, "texte": documents.read_text_file}
            # Lecture et transcription sont bloquantes : on les sort de la boucle asyncio
            sections = await asyncio.to_thread(readers[source], path)
        sections = [s for s in sections if s["text"].strip()]
        if not sections:
            raise ValueError("Aucun texte n'a pu être extrait.")
        return {"sections": sections}

    def prepare(state: IngestState):
        full_text = "\n\n".join(s["text"] for s in state["sections"])
        parts = documents.split_for_llm(full_text)
        warnings = [f"Compte-rendu long : analysé en {len(parts)} parties."] if len(parts) > 1 else []
        return {"full_text": full_text, "parts": parts, "warnings": warnings}

    def fan_out(state: IngestState):
        """Map : une branche d'indexation + une branche d'extraction par partie, en parallèle."""
        total = len(state["parts"])
        return [Send("index", state)] + [
            Send("extract_part", {"part": part, "index": i, "total": total,
                                  "meeting_date": state["meeting_date"], "language": state["language"]})
            for i, part in enumerate(state["parts"])
        ]

    async def index(state: IngestState):
        chunks = documents.split_into_chunks(state["sections"])
        result = await mcp.call("index_meeting", {"meeting_id": state["meeting_id"], "chunks": chunks})
        return {"indexed": result["indexed"]}

    async def extract_part(state: PartState):
        day = date.fromisoformat(state["meeting_date"])
        part_info = f"la partie {state['index'] + 1}/{state['total']} de " if state["total"] > 1 else ""
        prompt = prompts.EXTRACTION.format(
            part_info=part_info, meeting_date=state["meeting_date"], weekday=WEEKDAYS[day.weekday()],
            lang=LANGUAGE_NAMES.get(state["language"], "français"), text=state["part"])
        extraction = await ainvoke_json([HumanMessage(prompt)], MeetingExtraction)
        return {"partials": [{"index": state["index"], **extraction.model_dump()}]}

    async def merge(state: IngestState):
        partials = sorted(state["partials"], key=lambda p: p["index"])
        tasks = [t for p in partials for t in p["tasks"]]
        if len(partials) == 1:
            return {"summary": partials[0]["summary"], "decisions": partials[0]["decisions"], "tasks": tasks}
        text = "\n\n".join(
            f"PARTIE {p['index'] + 1}\nRésumé : {p['summary']}\nDécisions : {p['decisions']}" for p in partials)
        merged = await ainvoke_json(
            [HumanMessage(prompts.MERGE.format(count=len(partials), partials=text,
                                               lang=LANGUAGE_NAMES.get(state["language"], "français")))],
            MergedSummary)
        return {"summary": merged.summary, "decisions": merged.decisions, "tasks": tasks}

    def normalize(state: IngestState):
        seen, tasks, warnings = set(), [], []
        for task in state["tasks"]:
            description = (task.get("description") or "").strip()
            key = (description.lower(), (task.get("assignee") or "").lower())
            if not description or key in seen:
                continue
            seen.add(key)
            due = task.get("due_date")
            try:
                due = date.fromisoformat(str(due)[:10]).isoformat() if due else None
            except ValueError:
                warnings.append(f"Échéance illisible ignorée pour « {description} » : {due}")
                due = None
            if due and due < state["meeting_date"]:
                warnings.append(f"Échéance antérieure à la réunion pour « {description} » ({due}) : à vérifier.")
            tasks.append({"description": description, "assignee": task.get("assignee"), "due_date": due})
        return {"tasks": tasks, "warnings": warnings}

    async def persist(state: IngestState):
        await mcp.call("complete_meeting", {
            "meeting_id": state["meeting_id"], "content": state["full_text"], "summary": state["summary"],
            "decisions": state["decisions"], "tasks": state["tasks"],
        })
        return {}

    graph = StateGraph(IngestState)
    graph.add_node("load", load)
    graph.add_node("prepare", prepare)
    graph.add_node("index", index, retry_policy=RetryPolicy(max_attempts=2))
    graph.add_node("extract_part", extract_part, retry_policy=LLM_RETRY)
    graph.add_node("merge", merge, retry_policy=LLM_RETRY)
    graph.add_node("normalize", normalize)
    graph.add_node("persist", persist)

    graph.add_edge(START, "load")
    graph.add_edge("load", "prepare")
    graph.add_conditional_edges("prepare", fan_out, ["index", "extract_part"])
    graph.add_edge("extract_part", "merge")
    graph.add_edge("merge", "normalize")
    graph.add_edge(["index", "normalize"], "persist")  # jointure : attend les deux branches
    graph.add_edge("persist", END)
    return graph.compile()


async def process_meeting(mcp, meeting_id, title, meeting_date, language, source_type, text=None, file_path=None):
    """Exécute le graphe ; en cas d'échec, la réunion passe en statut « error » avec le message."""
    graph = build_ingestion_graph(mcp)
    try:
        return await graph.ainvoke({
            "meeting_id": meeting_id, "title": title, "meeting_date": meeting_date, "language": language,
            "source_type": source_type, "text": text, "file_path": file_path, "partials": [], "warnings": [],
        })
    except Exception as error:  # noqa: BLE001
        await mcp.call("fail_meeting", {"meeting_id": meeting_id, "error": str(error) or type(error).__name__})
        return None
    finally:
        if file_path:
            Path(file_path).unlink(missing_ok=True)
