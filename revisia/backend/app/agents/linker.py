"""Agent « linker » (LangGraph) : relie les chapitres à leurs prérequis dans les chapitres PRÉCÉDENTS.

  gather ──► (des liens à valider ?) ──► validate ──► apply
         └──────────────── non ─────────────────────┘

- gather   : pour chaque chapitre du cours, l'outil MCP `find_prerequisite_candidates` propose les
             chapitres précédents (même cours ou cours antérieurs) qui enseignent ses prérequis :
             correspondance exacte du nom de la notion, ou proximité sémantique (embeddings).
             Les correspondances exactes sont acceptées directement.
- validate : un seul appel LLM vérifie les correspondances sémantiques (évite les faux liens
             sur un mot commun). Si le LLM échoue, seules les correspondances très proches sont gardées.
- apply    : crée les relations DEPENDS_ON via l'outil MCP `add_dependency` (qui refuse tout lien
             vers un chapitre qui ne précède pas).
"""
from typing import TypedDict

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph

from ..config import AUTO_LINK_SCORE
from ..schemas import LinkDecisions
from ..services.llm import LANGUAGE_NAMES, ainvoke_json
from . import prompts


class LinkState(TypedDict, total=False):
    course_id: int
    language: str
    chapters: list[dict]
    accepted: list[dict]  # {"chapter_id", "prerequisite_chapter_id", "reason", "concepts"}
    to_validate: list[dict]  # {"chapter": {...}, "candidates": [...]}
    links: list[dict]
    method: str


def build_linking_graph(mcp):
    async def gather(state: LinkState):
        chapters = await mcp.call("list_chapters", {"course_id": state["course_id"]})
        accepted, to_validate = [], []
        for chapter in chapters:
            candidates = await mcp.call("find_prerequisite_candidates", {"chapter_id": chapter["id"]})
            uncertain = []
            for candidate in candidates:
                exact = [m for m in candidate["matches"] if m["method"] == "exact"]
                if exact:
                    accepted.append({
                        "chapter_id": chapter["id"], "prerequisite_chapter_id": candidate["chapter_id"],
                        "concepts": [m["prerequisite"] for m in exact],
                        "reason": "Enseigne : " + ", ".join(m["prerequisite"] for m in exact)})
                else:
                    uncertain.append(candidate)
            if uncertain:
                to_validate.append({"chapter": chapter, "candidates": uncertain})
        return {"chapters": chapters, "accepted": accepted, "to_validate": to_validate}

    def needs_validation(state: LinkState):
        return "validate" if state["to_validate"] else "apply"

    async def validate(state: LinkState):
        allowed = {}
        blocks = []
        for item in state["to_validate"]:
            chapter = item["chapter"]
            lines = [f"CHAPITRE {chapter['id']} « {chapter['title']} » (cours « {chapter['course_title']} »)"]
            for c in item["candidates"]:
                matches = "; ".join(f"prérequis « {m['prerequisite']} » ≈ notion « {m['concept']} » ({m['score']})"
                                    for m in c["matches"])
                lines.append(f"  - candidat {c['chapter_id']} « {c['title']} » (cours « {c['course_title']} ») : {matches}")
                allowed[(chapter["id"], c["chapter_id"])] = c
            blocks.append("\n".join(lines))
        try:
            decisions = await ainvoke_json([HumanMessage(prompts.LINK_VALIDATION.format(
                candidates="\n\n".join(blocks), lang=LANGUAGE_NAMES.get(state.get("language", "fr"), "français")))],
                LinkDecisions)
            links = []
            for d in decisions.links:
                candidate = allowed.get((d.chapter_id, d.prerequisite_chapter_id))
                if candidate:  # le LLM ne peut valider que des liens proposés
                    links.append({"chapter_id": d.chapter_id, "prerequisite_chapter_id": d.prerequisite_chapter_id,
                                  "reason": d.reason, "concepts": [m["prerequisite"] for m in candidate["matches"]]})
            method = "llm"
        except Exception:  # noqa: BLE001 - repli déterministe
            links = [{"chapter_id": cid, "prerequisite_chapter_id": pid,
                      "reason": "Notion très proche : " + ", ".join(m["concept"] for m in c["matches"]),
                      "concepts": [m["prerequisite"] for m in c["matches"]]}
                     for (cid, pid), c in allowed.items() if c["best_score"] >= AUTO_LINK_SCORE]
            method = "score"
        return {"accepted": state["accepted"] + links, "method": method}

    async def apply(state: LinkState):
        created, seen = [], set()
        for link in state["accepted"]:
            key = (link["chapter_id"], link["prerequisite_chapter_id"])
            if key in seen:
                continue
            seen.add(key)
            try:
                await mcp.call("add_dependency", link)
                created.append(link)
            except Exception:  # noqa: BLE001 - un lien refusé (ordre) n'arrête pas les autres
                continue
        return {"links": created}

    graph = StateGraph(LinkState)
    graph.add_node("gather", gather)
    graph.add_node("validate", validate)
    graph.add_node("apply", apply)
    graph.add_edge(START, "gather")
    graph.add_conditional_edges("gather", needs_validation, ["validate", "apply"])
    graph.add_edge("validate", "apply")
    graph.add_edge("apply", END)
    return graph.compile()


async def link_course(mcp, course_id, language="fr"):
    result = await build_linking_graph(mcp).ainvoke({"course_id": course_id, "language": language})
    return {"links": result.get("links", []), "method": result.get("method", "exact")}
