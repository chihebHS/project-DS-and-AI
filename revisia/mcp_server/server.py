"""Serveur MCP de RevisIA : la seule porte d'accès aux cours, au graphe de connaissances et à l'index RAG.

Le backend FastAPI et ses agents LangGraph l'utilisent comme client MCP ; n'importe quel autre
client compatible MCP (assistant de bureau, IDE...) peut aussi s'y brancher.

Lancement :
    python -m mcp_server                                   # stdio (lancé par le backend en local)
    MCP_TRANSPORT=streamable-http python -m mcp_server     # HTTP sur :8765/mcp (Docker / K8s)
"""
import json
import logging
from functools import wraps

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import config, rag
from . import database as db
from .graph_store import get_store, slug

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [mcp] %(message)s")
log = logging.getLogger("revisia.mcp")

db.init_db()

mcp = FastMCP(
    "revisia",
    instructions=(
        "Cours d'un étudiant découpés en chapitres, avec un graphe de connaissances : notions enseignées "
        "(COVERS), compétences à acquérir (TEACHES), prérequis (REQUIRES) et dépendances entre chapitres "
        "(DEPENDS_ON, toujours vers un chapitre qui précède). search_courses fait une recherche sémantique."
    ),
    host=config.MCP_HOST,
    port=config.MCP_PORT,
)


def to_json(data):
    return json.dumps(data, ensure_ascii=False, default=str)


def safe(func):
    """Les erreurs métier sont renvoyées en JSON {"error", "code"} au lieu de faire planter l'outil."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return to_json(func(*args, **kwargs))
        except db.NotFound as error:
            return to_json({"error": str(error), "code": 404})
        except ValueError as error:
            return to_json({"error": str(error), "code": 400})
        except Exception as error:  # noqa: BLE001 - filet de sécurité
            log.exception("Erreur dans l'outil %s", func.__name__)
            return to_json({"error": str(error), "code": 500})

    return wrapper


def store():
    return get_store()


# ---------- Recherche (RAG) ----------

@mcp.tool()
@safe
def search_courses(query: str, k: int = 4, course_id: int = 0) -> str:
    """Recherche sémantique dans le texte des cours. Renvoie les passages les plus pertinents avec le
    titre du cours, la position (page / minute) et un score. course_id (optionnel) limite à un cours."""
    return rag.search(query, k=max(1, min(k, 10)), course_id=course_id or None)


# ---------- Cours ----------

@mcp.tool()
@safe
def list_courses() -> str:
    """Liste les cours dans l'ordre du cursus (position), avec leur nombre de chapitres et leur statut."""
    return db.list_courses()


@mcp.tool()
@safe
def get_course(course_id: int, include_content: bool = False) -> str:
    """Détail d'un cours : résumé, notions clés, quiz et chapitres. include_content ajoute le texte complet."""
    return db.get_course(course_id, with_content=include_content)


@mcp.tool()
@safe
def create_course(title: str, language: str = "fr", source_type: str = "texte", filename: str = "") -> str:
    """Crée un cours vide (statut « processing ») avant son analyse. Il est placé en fin de cursus."""
    if not title.strip():
        raise ValueError("Le titre est vide")
    return {"id": db.create_course(title.strip(), language, source_type, filename or None)}


@mcp.tool()
@safe
def index_course(course_id: int, chunks: list[dict]) -> str:
    """Indexe les morceaux d'un cours pour la recherche sémantique. chunks : [{"label", "text"}]."""
    course = db.get_course(course_id, with_content=False)
    return {"indexed": rag.index_course(course_id, course["title"], chunks)}


@mcp.tool()
@safe
def save_course_analysis(course_id: int, content: str, summary: str, key_concepts: list[dict],
                         quiz: list[dict], chapters: list[dict]) -> str:
    """Enregistre l'analyse d'un cours et construit son graphe de connaissances.
    chapters (dans l'ordre) : [{"title", "summary", "label", "concepts": [{"name", "definition"}],
    "skills": ["compétence"], "prerequisites": ["notion à connaître avant"]}]."""
    db.get_course(course_id, with_content=False)
    ids = db.replace_chapters(course_id, chapters)
    db.update_course(course_id, content=content, summary=summary, key_concepts=key_concepts, quiz=quiz,
                     status="ready", error=None)
    course = db.get_course(course_id, with_content=False)
    enriched = [{**chapter, "id": cid, "position": i} for i, (chapter, cid) in enumerate(zip(chapters, ids,
                                                                                            strict=True), start=1)]
    store().save_course_graph(course, enriched)
    rag.index_concepts(course_id, enriched)
    return {"course_id": course_id, "chapters": [{"id": c["id"], "position": c["position"], "title": c["title"]}
                                                 for c in enriched]}


@mcp.tool()
@safe
def fail_course(course_id: int, error: str) -> str:
    """Marque l'analyse d'un cours comme échouée, avec le message d'erreur."""
    db.update_course(course_id, status="error", error=error[:1000])
    return {"course_id": course_id, "status": "error"}


@mcp.tool()
@safe
def delete_course(course_id: int) -> str:
    """Supprime un cours, ses chapitres, son sous-graphe et son index de recherche."""
    db.delete_course(course_id)
    store().delete_course_graph(course_id)
    rag.remove_course(course_id)
    return {"deleted": course_id}


@mcp.tool()
@safe
def move_course(course_id: int, position: int) -> str:
    """Change la place d'un cours dans le cursus (1 = premier). Les dépendances qui ne respectent plus
    l'ordre (un chapitre ne peut dépendre que d'un chapitre précédent) sont supprimées."""
    courses = db.move_course(course_id, position)
    removed = prune_invalid_dependencies()
    return {"courses": courses, "dependencies_removed": removed}


# ---------- Chapitres et graphe ----------

@mcp.tool()
@safe
def get_chapter(chapter_id: int) -> str:
    """Un chapitre avec ses notions (covers), compétences à acquérir (teaches), prérequis (requires),
    les chapitres dont il dépend (depends_on) et ceux qui dépendent de lui (required_by)."""
    return {**db.get_chapter(chapter_id), **store().chapter_knowledge(chapter_id)}


@mcp.tool()
@safe
def list_chapters(course_id: int = 0) -> str:
    """Liste les chapitres (d'un cours, ou de tous les cours) dans l'ordre du cursus."""
    return db.list_chapters(course_id or None)


@mcp.tool()
@safe
def find_prerequisite_candidates(chapter_id: int) -> str:
    """Pour chaque prérequis du chapitre, cherche les chapitres QUI LE PRÉCÈDENT et qui enseignent cette
    notion : correspondance exacte du nom, ou proximité sémantique (embeddings). Renvoie les candidats
    triés par score, à valider avant d'appeler add_dependency."""
    chapter = db.get_chapter(chapter_id)
    knowledge = store().chapter_knowledge(chapter_id)
    chapters = {c["id"]: c for c in db.list_chapters()}
    candidates = {}

    def add(candidate_id, prerequisite, concept, score, method):
        other = chapters.get(candidate_id)
        if not other or other["id"] == chapter_id or not db.precedes(other, chapter):
            return
        entry = candidates.setdefault(candidate_id, {
            "chapter_id": candidate_id, "title": other["title"], "course_id": other["course_id"],
            "course_title": other["course_title"], "same_course": other["course_id"] == chapter["course_id"],
            "matches": [], "best_score": 0.0})
        if not any(m["prerequisite"] == prerequisite for m in entry["matches"]):
            entry["matches"].append({"prerequisite": prerequisite, "concept": concept, "score": score,
                                     "method": method})
            entry["best_score"] = max(entry["best_score"], score)

    for requirement in knowledge["requires"]:
        for hit in store().chapters_covering([requirement["key"]]):
            add(hit["chapter_id"], requirement["name"], requirement["name"], 1.0, "exact")
        for hit in rag.search_concepts(requirement["name"]):
            if hit["score"] >= config.LINK_MIN_SCORE:
                add(hit["chapter_id"], requirement["name"], hit["name"], hit["score"], "semantic")
    return sorted(candidates.values(), key=lambda c: -c["best_score"])


@mcp.tool()
@safe
def add_dependency(chapter_id: int, prerequisite_chapter_id: int, reason: str = "",
                   concepts: list[str] | None = None) -> str:
    """Déclare que chapter_id dépend de prerequisite_chapter_id (relation DEPENDS_ON).
    Refusé si le chapitre prérequis ne précède pas le chapitre dans le cursus."""
    chapter, prerequisite = db.get_chapter(chapter_id), db.get_chapter(prerequisite_chapter_id)
    if not db.precedes(prerequisite, chapter):
        raise ValueError("Un chapitre ne peut dépendre que d'un chapitre qui le précède dans le cursus")
    store().add_dependency(chapter_id, prerequisite_chapter_id, reason, concepts)
    return {"chapter_id": chapter_id, "depends_on": prerequisite_chapter_id, "reason": reason}


@mcp.tool()
@safe
def remove_dependency(chapter_id: int, prerequisite_chapter_id: int) -> str:
    """Supprime une relation DEPENDS_ON."""
    store().remove_dependency(chapter_id, prerequisite_chapter_id)
    return {"removed": [chapter_id, prerequisite_chapter_id]}


@mcp.tool()
@safe
def learning_path(chapter_id: int) -> str:
    """Parcours de révision pour un chapitre : tous les chapitres prérequis (directs et indirects), dans
    l'ordre où les étudier, puis le chapitre lui-même. Inclut les notions à maîtriser."""
    target = db.get_chapter(chapter_id)
    depth = store().ancestors(chapter_id)
    deps = store().dependencies()
    steps = []
    for cid in sorted(depth, key=lambda c: db.rank(db.get_chapter(c))):
        chapter = db.get_chapter(cid)
        reasons = [d for d in deps if d["to"] == cid and (d["from"] == chapter_id or d["from"] in depth)]
        steps.append({"chapter_id": cid, "title": chapter["title"], "course_title": chapter["course_title"],
                      "distance": depth[cid], "concepts": sorted({c for d in reasons for c in d.get("concepts", [])}),
                      "reasons": [d.get("reason", "") for d in reasons if d.get("reason")]})
    knowledge = store().chapter_knowledge(chapter_id)
    steps.append({"chapter_id": chapter_id, "title": target["title"], "course_title": target["course_title"],
                  "distance": 0, "concepts": [c["name"] for c in knowledge["covers"]], "reasons": [], "target": True})
    return {"target": target["title"], "steps": steps,
            "skills": [s["name"] for s in knowledge["teaches"]],
            "prerequisites": [r["name"] for r in knowledge["requires"]]}


@mcp.tool()
@safe
def get_knowledge_graph(course_id: int = 0, node_types: list[str] | None = None) -> str:
    """Le graphe de connaissances (nœuds et relations), pour un cours ou pour tout le cursus.
    node_types (optionnel) : sous-ensemble de Course, Chapter, Concept, Skill."""
    return store().subgraph(course_id or None, node_types or None)


@mcp.tool()
@safe
def graph_stats() -> str:
    """Nombre de nœuds par type et de relations par type, et le moteur utilisé (sqlite ou neo4j)."""
    return store().stats()


@mcp.tool()
@safe
def find_concept(name: str) -> str:
    """Où une notion est-elle enseignée (COVERS) et quels chapitres la demandent en prérequis (REQUIRES) ?"""
    key = f"concept:{slug(name)}"
    chapters = {c["id"]: c for c in db.list_chapters()}
    taught, required = [], []
    for edge in store().edges():
        if edge["target"] == key and edge["type"] in ("COVERS", "REQUIRES"):
            chapter = chapters.get(int(edge["source"].split(":")[1]))
            if chapter:
                item = {"chapter_id": chapter["id"], "title": chapter["title"], "course_title": chapter["course_title"]}
                (taught if edge["type"] == "COVERS" else required).append(item)
    similar = [{"name": h["name"], "chapter_id": h["chapter_id"], "score": h["score"]} for h in rag.search_concepts(name, 5)]
    return {"concept": name, "taught_in": taught, "required_by": required, "similar": similar}


def prune_invalid_dependencies():
    chapters = {c["id"]: c for c in db.list_chapters()}
    removed = 0
    for dep in store().dependencies():
        source, target = chapters.get(dep["from"]), chapters.get(dep["to"])
        if not source or not target or not db.precedes(target, source):
            store().remove_dependency(dep["from"], dep["to"])
            removed += 1
    return removed


# ---------- Ressources et prompts MCP ----------

@mcp.resource("revisia://graph/stats")
def stats_resource() -> str:
    """Statistiques du graphe de connaissances."""
    return to_json(store().stats())


@mcp.prompt()
def revision_plan(chapter_title: str, language: str = "fr") -> str:
    """Prompt prêt à l'emploi : construire un plan de révision pour un chapitre."""
    return (
        f"Construis en {'français' if language == 'fr' else 'anglais'} un plan de révision pour le chapitre "
        f"« {chapter_title} » : utilise list_chapters pour trouver son id, puis learning_path, et propose "
        "un ordre d'étude avec pour chaque étape les notions à revoir et un exercice."
    )


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> JSONResponse:
    """Sonde de vie/disponibilité pour Kubernetes (transport HTTP uniquement)."""
    return JSONResponse({"status": "ok", "graph": store().backend})


def main():
    log.info("Serveur MCP RevisIA (transport=%s, données=%s, graphe=%s)", config.MCP_TRANSPORT, config.DATA_DIR,
             "neo4j" if config.NEO4J_URI else "sqlite")
    rag.warmup()
    connect_graph()
    mcp.run(transport=config.MCP_TRANSPORT)


def connect_graph(retries=30, delay=2.0):
    """En conteneur, Neo4j peut démarrer après le serveur MCP : on réessaie avant d'abandonner."""
    import time

    for attempt in range(1, retries + 1):
        try:
            return store()
        except Exception as error:  # noqa: BLE001
            if attempt == retries:
                raise
            log.warning("Graphe indisponible (%s), nouvel essai dans %.0fs", error, delay)
            from .graph_store import reset_store

            reset_store()
            time.sleep(delay)


if __name__ == "__main__":
    main()
