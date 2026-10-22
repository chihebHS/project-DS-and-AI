"""Serveur MCP de RecrutIA.

Il expose les données RH locales (CV, postes, suivi des candidats) sous forme d'OUTILS.
Un client MCP (notre backend, ou n'importe quel client compatible MCP) peut appeler ces
outils, mais n'a jamais accès directement aux fichiers ni à la base de données.

Lancement seul (pour tester) :  python mcp_server/server.py
"""
import base64
import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

import storage

storage.init_db()
mcp = FastMCP("recrutia-rh")


def to_json(data):
    # Chaque outil renvoie du JSON texte : simple à lire pour le LLM comme pour le backend
    return json.dumps(data, ensure_ascii=False, indent=1)


# ---------- CV et candidats ----------

@mcp.tool()
def upload_cv(filename: str, content_base64: str) -> str:
    """Dépose un fichier CV (PDF, DOCX ou TXT, encodé en base64) dans le dossier local des CV,
    puis l'ajoute au suivi des candidats."""
    path = storage.CV_DIR / Path(filename).name  # on garde seulement le nom, pas de chemin
    if path.suffix.lower() not in storage.CV_EXTENSIONS:
        return to_json({"error": f"Format non supporté : {path.suffix}"})
    if path.exists():
        return to_json({"error": f"Le fichier {path.name} existe déjà"})
    path.write_bytes(base64.b64decode(content_base64))
    return to_json({"added": storage.import_new_cvs()})


@mcp.tool()
def import_cvs() -> str:
    """Analyse le dossier local des CV et ajoute au suivi les nouveaux candidats."""
    return to_json({"added": storage.import_new_cvs()})


@mcp.tool()
def list_candidates(status: str = "") -> str:
    """Liste les candidats (sans le contenu du CV).
    status (optionnel) : nouveau, preselectionne, entretien, refuse ou embauche."""
    return to_json(storage.list_candidates(status or None))


@mcp.tool()
def read_cv(candidate_id: int) -> str:
    """Renvoie le texte complet du CV d'un candidat, son statut et les notes des recruteurs."""
    candidate = storage.get_candidate(candidate_id)
    return to_json(candidate or {"error": "Candidat introuvable"})


@mcp.tool()
def search_candidates(query: str, limit: int = 5) -> str:
    """Recherche sémantique dans les CV : renvoie les candidats dont le profil
    correspond le mieux à la requête (compétences, poste, expérience...), avec un score de similarité."""
    return to_json(storage.search_candidates(query, limit))


@mcp.tool()
def update_candidate_status(candidate_id: int, status: str) -> str:
    """Change l'étape d'un candidat dans le processus de recrutement.
    status : nouveau, preselectionne, entretien, refuse ou embauche."""
    try:
        storage.set_status(candidate_id, status)
        return to_json({"ok": True, "candidate_id": candidate_id, "status": status})
    except ValueError as error:
        return to_json({"error": str(error)})


@mcp.tool()
def add_candidate_note(candidate_id: int, note: str) -> str:
    """Ajoute une note de recruteur sur un candidat."""
    try:
        return to_json({"notes": storage.add_note(candidate_id, note)})
    except ValueError as error:
        return to_json({"error": str(error)})


@mcp.tool()
def delete_candidate(candidate_id: int) -> str:
    """Supprime un candidat et son CV."""
    storage.delete_candidate(candidate_id)
    return to_json({"deleted": candidate_id})


# ---------- Postes ----------

@mcp.tool()
def list_jobs() -> str:
    """Liste les fiches de poste ouvertes."""
    return to_json(storage.list_jobs())


@mcp.tool()
def get_job(job_id: int) -> str:
    """Renvoie une fiche de poste complète (titre, description, compétences)."""
    return to_json(storage.get_job(job_id) or {"error": "Poste introuvable"})


@mcp.tool()
def create_job(title: str, description: str, skills: str = "") -> str:
    """Crée une nouvelle fiche de poste. skills : compétences séparées par des virgules."""
    return to_json({"id": storage.create_job(title, description, skills)})


@mcp.tool()
def delete_job(job_id: int) -> str:
    """Supprime une fiche de poste."""
    storage.delete_job(job_id)
    return to_json({"deleted": job_id})


@mcp.tool()
def pipeline_stats() -> str:
    """Statistiques du recrutement : nombre de postes et de candidats par étape."""
    return to_json(storage.pipeline_stats())


if __name__ == "__main__":
    # Transport stdio : le client lance ce script et communique via l'entrée/sortie standard
    mcp.run()
