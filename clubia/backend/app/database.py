"""Base de données SQLite : réunions et tâches du club."""
import json
import sqlite3
from datetime import date, datetime

from .config import DB_PATH


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meetings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                meeting_date TEXT NOT NULL,
                language TEXT NOT NULL,
                source_type TEXT NOT NULL,
                content TEXT,
                summary TEXT,
                decisions TEXT,
                status TEXT DEFAULT 'pending',
                error TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
                description TEXT NOT NULL,
                assignee TEXT,
                due_date TEXT,
                status TEXT DEFAULT 'a_faire',
                updated_at TEXT
            )
            """
        )


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------- Réunions ----------

def create_meeting(title, meeting_date, language, source_type):
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO meetings (title, meeting_date, language, source_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (title, meeting_date, language, source_type, now()),
        )
        return cursor.lastrowid


def update_meeting(meeting_id, **fields):
    if "decisions" in fields:
        fields["decisions"] = json.dumps(fields["decisions"], ensure_ascii=False)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with get_connection() as conn:
        conn.execute(f"UPDATE meetings SET {columns} WHERE id = ?", (*fields.values(), meeting_id))


def get_meeting(meeting_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if row is None:
        return None
    meeting = dict(row)
    meeting["decisions"] = json.loads(meeting["decisions"] or "[]")
    meeting["tasks"] = list_tasks(meeting_id=meeting_id)
    return meeting


def list_meetings():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, meeting_date, source_type, status FROM meetings ORDER BY meeting_date DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_meeting(meeting_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))


# ---------- Tâches ----------

def add_task(meeting_id, description, assignee, due_date):
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (meeting_id, description, assignee, due_date, updated_at) VALUES (?, ?, ?, ?, ?)",
            (meeting_id, description, assignee or "Non attribué", due_date or None, now()),
        )
        return cursor.lastrowid


def list_tasks(meeting_id=None, status=None, assignee=None):
    query = """
        SELECT tasks.*, meetings.title AS meeting_title, meetings.meeting_date
        FROM tasks LEFT JOIN meetings ON meetings.id = tasks.meeting_id
        WHERE 1 = 1
    """
    params = []
    if meeting_id:
        query += " AND tasks.meeting_id = ?"
        params.append(meeting_id)
    if status:
        query += " AND tasks.status = ?"
        params.append(status)
    if assignee:
        query += " AND tasks.assignee = ?"
        params.append(assignee)
    # Les tâches sans échéance passent à la fin
    query += " ORDER BY tasks.due_date IS NULL, tasks.due_date, tasks.id"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    today = date.today().isoformat()
    tasks = []
    for row in rows:
        task = dict(row)
        task["overdue"] = bool(task["due_date"] and task["due_date"] < today and task["status"] != "termine")
        tasks.append(task)
    return tasks


def update_task(task_id, **fields):
    fields["updated_at"] = now()
    columns = ", ".join(f"{key} = ?" for key in fields)
    with get_connection() as conn:
        conn.execute(f"UPDATE tasks SET {columns} WHERE id = ?", (*fields.values(), task_id))


def delete_task(task_id):
    with get_connection() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))


def get_stats():
    tasks = list_tasks()
    members = {}
    for task in tasks:
        stats = members.setdefault(task["assignee"], {"name": task["assignee"], "total": 0, "done": 0, "overdue": 0})
        stats["total"] += 1
        stats["done"] += task["status"] == "termine"
        stats["overdue"] += task["overdue"]
    return {
        "meetings": len(list_meetings()),
        "tasks_total": len(tasks),
        "tasks_todo": sum(t["status"] == "a_faire" for t in tasks),
        "tasks_in_progress": sum(t["status"] == "en_cours" for t in tasks),
        "tasks_done": sum(t["status"] == "termine" for t in tasks),
        "tasks_overdue": sum(t["overdue"] for t in tasks),
        "members": sorted(members.values(), key=lambda m: -m["total"]),
        "upcoming": [t for t in tasks if t["status"] != "termine"][:5],
    }
