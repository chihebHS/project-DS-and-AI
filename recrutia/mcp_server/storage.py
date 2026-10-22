"""Stockage local de l'entreprise : CV (fichiers), mini-ATS (SQLite) et index sémantique (ChromaDB).

Ce module n'est utilisé QUE par le serveur MCP. Le reste de l'application (et le LLM)
n'accède jamais directement à ces données : il doit passer par les outils MCP.
"""
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import chromadb
from docx import Document
from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CV_DIR = DATA_DIR / "cvs"            # dossier où l'entreprise dépose ses CV
DB_PATH = DATA_DIR / "ats.db"        # mini-ATS : candidats, postes, notes
CHROMA_DIR = DATA_DIR / "chroma"     # index pour la recherche sémantique

for folder in (DATA_DIR, CV_DIR, CHROMA_DIR):
    folder.mkdir(parents=True, exist_ok=True)

CV_EXTENSIONS = {".pdf", ".docx", ".txt"}
STATUSES = ("nouveau", "preselectionne", "entretien", "refuse", "embauche")

_chroma = chromadb.PersistentClient(path=str(CHROMA_DIR))
_cv_index = _chroma.get_or_create_collection("cvs")


# ---------- Base de données ----------

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT,
                filename TEXT UNIQUE NOT NULL,
                content TEXT,
                status TEXT DEFAULT 'nouveau',
                notes TEXT DEFAULT '[]',
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                skills TEXT,
                created_at TEXT
            )
            """
        )


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- Lecture des CV ----------

def read_cv_file(path: Path) -> str:
    if path.suffix == ".pdf":
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages).strip()
    if path.suffix == ".docx":
        return "\n".join(p.text for p in Document(path).paragraphs).strip()
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def name_from_filename(path: Path) -> str:
    # "Sarah_Benali_CV.pdf" -> "Sarah Benali"
    words = re.split(r"[_\-\s]+", path.stem)
    words = [w for w in words if w.lower() not in ("cv", "resume", "curriculum")]
    return " ".join(w.capitalize() for w in words) or path.stem


def find_email(text: str):
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    return match.group(0) if match else None


def import_new_cvs():
    """Parcourt le dossier des CV et ajoute au mini-ATS ceux qui n'y sont pas encore."""
    added = []
    with connect() as conn:
        known = {row["filename"] for row in conn.execute("SELECT filename FROM candidates")}
        for path in sorted(CV_DIR.iterdir()):
            if path.suffix.lower() not in CV_EXTENSIONS or path.name in known:
                continue
            text = read_cv_file(path)
            if not text:
                continue
            cursor = conn.execute(
                "INSERT INTO candidates (name, email, filename, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (name_from_filename(path), find_email(text), path.name, text, now()),
            )
            candidate_id = cursor.lastrowid
            # Un CV = un document dans l'index (les CV sont courts)
            _cv_index.add(ids=[str(candidate_id)], documents=[text[:4000]], metadatas=[{"candidate_id": candidate_id}])
            added.append({"id": candidate_id, "name": name_from_filename(path)})
    return added


# ---------- Candidats ----------

def candidate_summary(row):
    return {"id": row["id"], "name": row["name"], "email": row["email"], "status": row["status"],
            "filename": row["filename"], "created_at": row["created_at"]}


def list_candidates(status=None):
    query, params = "SELECT * FROM candidates", []
    if status:
        query += " WHERE status = ?"
        params.append(status)
    with connect() as conn:
        rows = conn.execute(query + " ORDER BY id DESC", params).fetchall()
    return [candidate_summary(row) for row in rows]


def get_candidate(candidate_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM candidates WHERE id = ?", (candidate_id,)).fetchone()
    if row is None:
        return None
    candidate = candidate_summary(row)
    candidate["cv_text"] = row["content"]
    candidate["notes"] = json.loads(row["notes"])
    return candidate


def search_candidates(query, limit=5):
    """Recherche sémantique : les CV dont le sens est le plus proche de la requête."""
    count = _cv_index.count()
    if count == 0:
        return []
    results = _cv_index.query(query_texts=[query], n_results=min(limit, count))
    found = []
    for meta, distance in zip(results["metadatas"][0], results["distances"][0]):
        candidate = get_candidate(meta["candidate_id"])
        if candidate:
            # La distance est convertie en un score de similarité entre 0 et 100
            similarity = round(max(0.0, 1 - distance / 2) * 100)
            found.append({**candidate_summary_from(candidate), "similarity": similarity})
    return found


def candidate_summary_from(candidate):
    return {key: candidate[key] for key in ("id", "name", "email", "status", "filename")}


def set_status(candidate_id, status):
    if status not in STATUSES:
        raise ValueError(f"Statut invalide. Choix possibles : {', '.join(STATUSES)}")
    with connect() as conn:
        conn.execute("UPDATE candidates SET status = ? WHERE id = ?", (status, candidate_id))


def add_note(candidate_id, text):
    candidate = get_candidate(candidate_id)
    if candidate is None:
        raise ValueError("Candidat introuvable")
    notes = candidate["notes"] + [{"date": now(), "text": text}]
    with connect() as conn:
        conn.execute("UPDATE candidates SET notes = ? WHERE id = ?", (json.dumps(notes, ensure_ascii=False), candidate_id))
    return notes


def delete_candidate(candidate_id):
    candidate = get_candidate(candidate_id)
    if candidate is None:
        return
    _cv_index.delete(ids=[str(candidate_id)])
    with connect() as conn:
        conn.execute("DELETE FROM candidates WHERE id = ?", (candidate_id,))
    (CV_DIR / candidate["filename"]).unlink(missing_ok=True)


# ---------- Postes ----------

def list_jobs():
    with connect() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM jobs ORDER BY id DESC").fetchall()]


def get_job(job_id):
    with connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def create_job(title, description, skills):
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO jobs (title, description, skills, created_at) VALUES (?, ?, ?, ?)",
            (title, description, skills, now()),
        )
        return cursor.lastrowid


def delete_job(job_id):
    with connect() as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


def pipeline_stats():
    with connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM candidates GROUP BY status").fetchall()
        jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    counts = {status: 0 for status in STATUSES}
    counts.update({row["status"]: row["n"] for row in rows})
    return {"jobs": jobs, "candidates": sum(counts.values()), "by_status": counts}
