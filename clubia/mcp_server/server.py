"""Serveur MCP de ClubIA : la seule porte d'accès aux données du club.

Il expose les réunions, les tâches, les membres et la recherche sémantique (RAG) sous forme
d'OUTILS MCP. Le backend FastAPI et les agents LangGraph l'utilisent comme client MCP ;
n'importe quel autre client compatible MCP (assistant de bureau, IDE...) peut aussi s'y brancher.

Lancement :
    python -m mcp_server                       # stdio (lancé par le backend en local)
    MCP_TRANSPORT=streamable-http python -m mcp_server   # HTTP sur :8765/mcp (Docker / K8s)
"""
import json
import logging
from functools import wraps

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import config, rag
from . import database as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [mcp] %(message)s")
log = logging.getLogger("clubia.mcp")

db.init_db()

mcp = FastMCP(
    "clubia",
    instructions=(
        "Données d'un club étudiant : réunions (résumé, décisions), tâches (responsable, échéance, "
        "statut a_faire/en_cours/termine, retard) et membres. search_meetings fait une recherche "
        "sémantique dans les comptes-rendus."
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
        except Exception as error:  # pragma: no cover - filet de sécurité
            log.exception("Erreur dans l'outil %s", func.__name__)
            return to_json({"error": str(error), "code": 500})

    return wrapper


# ---------- Recherche (RAG) ----------

@mcp.tool()
@safe
def search_meetings(query: str, k: int = 4, meeting_id: int = 0) -> str:
    """Recherche sémantique dans les comptes-rendus des réunions.
    Renvoie les passages les plus pertinents avec le titre, la date, la position (page/minute)
    et un score de similarité. meeting_id (optionnel) limite la recherche à une réunion."""
    return rag.search(query, k=max(1, min(k, 10)), meeting_id=meeting_id or None)


# ---------- Réunions ----------

@mcp.tool()
@safe
def list_meetings() -> str:
    """Liste les réunions (id, titre, date, type de source, statut de l'analyse)."""
    return db.list_meetings()


@mcp.tool()
@safe
def get_meeting(meeting_id: int, include_content: bool = False) -> str:
    """Détail d'une réunion : résumé, décisions et tâches. include_content ajoute le texte complet."""
    return db.get_meeting(meeting_id, with_content=include_content)


@mcp.tool()
@safe
def create_meeting(title: str, meeting_date: str = "", language: str = "fr", source_type: str = "saisie") -> str:
    """Crée une réunion vide (statut « processing ») avant son analyse. Renvoie son id."""
    if not title.strip():
        raise ValueError("Le titre est vide")
    return {"id": db.create_meeting(title.strip(), meeting_date, language, source_type)}


@mcp.tool()
@safe
def index_meeting(meeting_id: int, chunks: list[dict]) -> str:
    """Indexe les morceaux d'un compte-rendu pour la recherche sémantique.
    chunks : liste de {"label": "page 2" | "à 03:00" | ..., "text": "..."}."""
    meeting = db.get_meeting(meeting_id, with_content=False)
    return {"indexed": rag.index_meeting(meeting_id, meeting["title"], meeting["meeting_date"], chunks)}


@mcp.tool()
@safe
def complete_meeting(meeting_id: int, content: str, summary: str, decisions: list[str], tasks: list[dict]) -> str:
    """Enregistre le résultat de l'analyse d'une réunion : texte, résumé, décisions et tâches
    ({"description", "assignee", "due_date"}). Les responsables sont rattachés aux membres connus."""
    db.get_meeting(meeting_id, with_content=False)
    created = []
    for task in tasks:
        if (task.get("description") or "").strip():
            created.append(db.add_task(meeting_id, task["description"], task.get("assignee"), task.get("due_date")))
    db.update_meeting(meeting_id, content=content, summary=summary, decisions=decisions, status="ready", error=None)
    return {"meeting_id": meeting_id, "tasks_created": len(created)}


@mcp.tool()
@safe
def fail_meeting(meeting_id: int, error: str) -> str:
    """Marque l'analyse d'une réunion comme échouée, avec le message d'erreur."""
    db.update_meeting(meeting_id, status="error", error=error[:1000])
    return {"meeting_id": meeting_id, "status": "error"}


@mcp.tool()
@safe
def delete_meeting(meeting_id: int) -> str:
    """Supprime une réunion, ses tâches et son index de recherche."""
    db.delete_meeting(meeting_id)
    rag.remove_meeting(meeting_id)
    return {"deleted": meeting_id}


# ---------- Tâches ----------

@mcp.tool()
@safe
def list_tasks(status: str = "", assignee: str = "", meeting_id: int = 0, overdue_only: bool = False) -> str:
    """Liste les tâches à jour, avec leur retard éventuel.
    Filtres optionnels : status (a_faire, en_cours, termine), assignee (nom du membre),
    meeting_id, overdue_only (seulement les tâches en retard)."""
    return db.list_tasks(meeting_id=meeting_id or None, status=status or None,
                         assignee=assignee or None, overdue_only=overdue_only)


@mcp.tool()
@safe
def create_task(description: str, assignee: str = "", due_date: str = "", meeting_id: int = 0) -> str:
    """Crée une tâche. due_date au format AAAA-MM-JJ. Le responsable est rattaché aux membres connus."""
    return db.add_task(meeting_id or None, description, assignee, due_date)


@mcp.tool()
@safe
def update_task(task_id: int, status: str = "", assignee: str = "", due_date: str = "", description: str = "") -> str:
    """Modifie une tâche : seuls les champs non vides sont changés.
    status : a_faire, en_cours ou termine. due_date : AAAA-MM-JJ, ou « none » pour retirer l'échéance."""
    changes = {k: v for k, v in {"status": status, "assignee": assignee, "description": description}.items() if v}
    if due_date:
        changes["due_date"] = None if due_date.lower() in {"none", "null", "aucune"} else due_date
    return db.update_task(task_id, **changes)


@mcp.tool()
@safe
def delete_task(task_id: int) -> str:
    """Supprime une tâche."""
    return {"deleted": db.delete_task(task_id)["id"]}


@mcp.tool()
@safe
def get_stats() -> str:
    """Statistiques du club : nombre de réunions, tâches par statut, retards, charge par membre,
    5 prochaines échéances."""
    return db.get_stats()


# ---------- Membres ----------

@mcp.tool()
@safe
def list_members() -> str:
    """Liste les membres du club avec leurs alias (autres façons d'écrire leur nom)."""
    return db.list_members()


@mcp.tool()
@safe
def create_member(name: str, aliases: list[str] | None = None, email: str = "") -> str:
    """Ajoute un membre au club."""
    return db.create_member(name, aliases or [], email or None)


@mcp.tool()
@safe
def update_member(member_id: int, name: str = "", aliases: list[str] | None = None, email: str = "") -> str:
    """Modifie un membre (nom, alias, e-mail). Renommer un membre met à jour ses tâches."""
    return db.update_member(member_id, name=name or None, aliases=aliases, email=email or None)


@mcp.tool()
@safe
def delete_member(member_id: int) -> str:
    """Supprime un membre : ses tâches passent à « Non attribué »."""
    return {"deleted": db.delete_member(member_id)["id"]}


@mcp.tool()
@safe
def merge_members(keep_id: int, other_id: int) -> str:
    """Fusionne deux fiches du même membre : les tâches et alias de other_id passent à keep_id."""
    return db.merge_members(keep_id, other_id)


# ---------- Ressources et prompts MCP ----------

@mcp.resource("clubia://tasks/overdue")
def overdue_tasks_resource() -> str:
    """Les tâches en retard, à jour."""
    return to_json(db.list_tasks(overdue_only=True))


@mcp.resource("clubia://stats")
def stats_resource() -> str:
    """Le tableau de bord du club."""
    return to_json(db.get_stats())


@mcp.prompt()
def weekly_report(language: str = "fr") -> str:
    """Prompt prêt à l'emploi : rédiger le point hebdomadaire du club."""
    return (
        f"Rédige en {'français' if language == 'fr' else 'anglais'} le point hebdomadaire du club : "
        "utilise get_stats et list_tasks(overdue_only=true), félicite ce qui est terminé, "
        "liste les retards avec leur responsable et propose 3 priorités pour la semaine."
    )


@mcp.custom_route("/healthz", methods=["GET"])
async def healthz(_: Request) -> JSONResponse:
    """Sonde de vie/disponibilité pour Kubernetes (transport HTTP uniquement)."""
    return JSONResponse({"status": "ok", "db": str(config.DB_PATH.name)})


def main():
    log.info("Serveur MCP ClubIA (transport=%s, données=%s)", config.MCP_TRANSPORT, config.DATA_DIR)
    rag.warmup()
    mcp.run(transport=config.MCP_TRANSPORT)


if __name__ == "__main__":
    main()
