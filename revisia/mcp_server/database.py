"""Base SQLite : cours (résumé, notions, quiz) et chapitres.

L'ordre compte : chaque cours a une position dans le cursus et chaque chapitre une position
dans son cours. Un chapitre ne peut dépendre que d'un chapitre qui le PRÉCÈDE dans cet ordre.
"""
import json
import sqlite3
from datetime import datetime

from . import config


class NotFound(LookupError):
    pass


def get_connection():
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    config.ensure_dirs()
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                language TEXT NOT NULL,
                source_type TEXT NOT NULL,
                filename TEXT,
                content TEXT,
                summary TEXT,
                key_concepts TEXT,
                quiz TEXT,
                position INTEGER NOT NULL DEFAULT 0,
                status TEXT DEFAULT 'processing',
                error TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                title TEXT NOT NULL,
                summary TEXT,
                label TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_chapters_course ON chapters(course_id, position);
            """
        )


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- Cours ----------

def _course_row(row):
    course = dict(row)
    course["key_concepts"] = json.loads(course.get("key_concepts") or "[]")
    course["quiz"] = json.loads(course.get("quiz") or "[]")
    return course


def create_course(title, language, source_type, filename=None):
    with get_connection() as conn:
        position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM courses").fetchone()[0]
        cursor = conn.execute(
            "INSERT INTO courses (title, language, source_type, filename, position, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'processing', ?)",
            (title, language, source_type, filename, position, now()),
        )
    return cursor.lastrowid


def update_course(course_id, **fields):
    for key in ("key_concepts", "quiz"):
        if key in fields:
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE courses SET {columns} WHERE id = ?", (*fields.values(), course_id))
    if cursor.rowcount == 0:
        raise NotFound(f"Cours {course_id} introuvable")


def get_course(course_id, with_content=True):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    if row is None:
        raise NotFound(f"Cours {course_id} introuvable")
    course = _course_row(row)
    course["chapters"] = list_chapters(course_id)
    if not with_content:
        course.pop("content", None)
    return course


def list_courses():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT c.id, c.title, c.language, c.source_type, c.status, c.position, c.created_at,"
            " (SELECT COUNT(*) FROM chapters WHERE course_id = c.id) AS chapters"
            " FROM courses c ORDER BY c.position, c.id"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_course(course_id):
    get_course(course_id, with_content=False)
    with get_connection() as conn:
        conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))


def move_course(course_id, position):
    """Place un cours à la position donnée (1 = premier) dans le cursus et renumérote les autres."""
    get_course(course_id, with_content=False)
    ids = [c["id"] for c in list_courses() if c["id"] != course_id]
    position = max(1, min(int(position), len(ids) + 1))
    ids.insert(position - 1, course_id)
    with get_connection() as conn:
        for index, cid in enumerate(ids, start=1):
            conn.execute("UPDATE courses SET position = ? WHERE id = ?", (index, cid))
    return list_courses()


# ---------- Chapitres ----------

def replace_chapters(course_id, chapters):
    """Remplace les chapitres d'un cours. chapters : [{"title", "summary", "label"}] dans l'ordre."""
    with get_connection() as conn:
        conn.execute("DELETE FROM chapters WHERE course_id = ?", (course_id,))
        ids = []
        for position, chapter in enumerate(chapters, start=1):
            cursor = conn.execute(
                "INSERT INTO chapters (course_id, position, title, summary, label) VALUES (?, ?, ?, ?, ?)",
                (course_id, position, chapter["title"], chapter.get("summary", ""), chapter.get("label")),
            )
            ids.append(cursor.lastrowid)
    return ids


def list_chapters(course_id=None):
    query = (
        "SELECT ch.*, c.title AS course_title, c.position AS course_position FROM chapters ch"
        " JOIN courses c ON c.id = ch.course_id"
    )
    params = ()
    if course_id:
        query += " WHERE ch.course_id = ?"
        params = (course_id,)
    with get_connection() as conn:
        rows = conn.execute(query + " ORDER BY c.position, ch.position", params).fetchall()
    return [dict(r) for r in rows]


def get_chapter(chapter_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT ch.*, c.title AS course_title, c.position AS course_position FROM chapters ch"
            " JOIN courses c ON c.id = ch.course_id WHERE ch.id = ?",
            (chapter_id,),
        ).fetchone()
    if row is None:
        raise NotFound(f"Chapitre {chapter_id} introuvable")
    return dict(row)


def rank(chapter):
    """Rang global d'un chapitre dans le cursus : (position du cours, position dans le cours)."""
    return (chapter["course_position"], chapter["position"])


def precedes(chapter_a, chapter_b):
    """Vrai si le chapitre A vient avant le chapitre B dans le cursus."""
    return rank(chapter_a) < rank(chapter_b)
