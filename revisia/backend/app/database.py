"""Base de données SQLite : stocke les cours et ce que l'IA a généré."""
import json
import sqlite3
from datetime import datetime

from .config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
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
                status TEXT DEFAULT 'pending',
                error TEXT,
                created_at TEXT
            )
            """
        )


def _row_to_dict(row):
    if row is None:
        return None
    course = dict(row)
    # Les listes sont stockées en JSON dans la base
    course["key_concepts"] = json.loads(course["key_concepts"] or "[]")
    course["quiz"] = json.loads(course["quiz"] or "[]")
    return course


def create_course(title, language, source_type, filename):
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO courses (title, language, source_type, filename, created_at) VALUES (?, ?, ?, ?, ?)",
            (title, language, source_type, filename, datetime.now().isoformat(timespec="seconds")),
        )
        return cursor.lastrowid


def update_course(course_id, **fields):
    for key in ("key_concepts", "quiz"):
        if key in fields:
            fields[key] = json.dumps(fields[key], ensure_ascii=False)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with get_connection() as conn:
        conn.execute(f"UPDATE courses SET {columns} WHERE id = ?", (*fields.values(), course_id))


def get_course(course_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
    return _row_to_dict(row)


def list_courses():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, language, source_type, status, created_at FROM courses ORDER BY id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_course(course_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
