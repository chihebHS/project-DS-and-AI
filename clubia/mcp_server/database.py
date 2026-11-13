"""Base SQLite du club : réunions, tâches et membres.

Seul le serveur MCP ouvre cette base : le backend et les agents passent par les outils MCP.
"""
import json
import sqlite3
from datetime import date, datetime

from . import config
from . import members as names
from .config import TASK_STATUSES, UNASSIGNED

TASK_FIELDS = {"description", "assignee", "due_date", "status"}
MEMBER_FIELDS = {"name", "aliases", "email"}


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
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meeting_id INTEGER REFERENCES meetings(id) ON DELETE CASCADE,
                description TEXT NOT NULL,
                assignee TEXT,
                due_date TEXT,
                status TEXT DEFAULT 'a_faire',
                updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE COLLATE NOCASE,
                aliases TEXT DEFAULT '[]',
                email TEXT,
                created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_tasks_meeting ON tasks(meeting_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            """
        )


def now():
    return datetime.now().isoformat(timespec="seconds")


def valid_date(value):
    """Renvoie la date au format AAAA-MM-JJ, ou None si elle est absente ou invalide."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10]).isoformat()
    except ValueError:
        return None


# ---------- Membres ----------

def _member_row(row):
    member = dict(row)
    member["aliases"] = json.loads(member["aliases"] or "[]")
    return member


def list_members():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM members ORDER BY name").fetchall()
    return [_member_row(r) for r in rows]


def get_member(member_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    if row is None:
        raise NotFound(f"Membre {member_id} introuvable")
    return _member_row(row)


def create_member(name, aliases=None, email=None):
    name = names.clean_display(name)
    if not name or names.is_unassigned(name):
        raise ValueError("Nom de membre invalide")
    with get_connection() as conn:
        try:
            cursor = conn.execute(
                "INSERT INTO members (name, aliases, email, created_at) VALUES (?, ?, ?, ?)",
                (name, json.dumps(aliases or [], ensure_ascii=False), email, now()),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Le membre « {name} » existe déjà") from error
    return get_member(cursor.lastrowid)


def update_member(member_id, **fields):
    member = get_member(member_id)
    fields = {k: v for k, v in fields.items() if k in MEMBER_FIELDS and v is not None}
    if "name" in fields:
        fields["name"] = names.clean_display(fields["name"])
        if not fields["name"]:
            raise ValueError("Nom de membre invalide")
    if "aliases" in fields:
        fields["aliases"] = json.dumps(sorted(set(fields["aliases"])), ensure_ascii=False)
    if not fields:
        return member
    columns = ", ".join(f"{key} = ?" for key in fields)
    with get_connection() as conn:
        try:
            conn.execute(f"UPDATE members SET {columns} WHERE id = ?", (*fields.values(), member_id))
        except sqlite3.IntegrityError as error:
            raise ValueError(f"Le membre « {fields['name']} » existe déjà") from error
        if "name" in fields and fields["name"] != member["name"]:
            _rename_in_tasks(conn, member["name"], fields["name"])
    return get_member(member_id)


def delete_member(member_id):
    member = get_member(member_id)
    with get_connection() as conn:
        _rename_in_tasks(conn, member["name"], UNASSIGNED)
        conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
    return member


def merge_members(keep_id, other_id):
    """Fusionne `other` dans `keep` : ses tâches et ses alias passent à `keep`."""
    if keep_id == other_id:
        raise ValueError("Impossible de fusionner un membre avec lui-même")
    keep, other = get_member(keep_id), get_member(other_id)
    aliases = set(keep["aliases"]) | set(other["aliases"]) | {other["name"]}
    with get_connection() as conn:
        _rename_in_tasks(conn, other["name"], keep["name"])
        conn.execute("DELETE FROM members WHERE id = ?", (other_id,))
        conn.execute(
            "UPDATE members SET aliases = ? WHERE id = ?",
            (json.dumps(sorted(aliases - {keep["name"]}), ensure_ascii=False), keep_id),
        )
    return get_member(keep_id)


def _rename_in_tasks(conn, old, new):
    rows = conn.execute("SELECT id, assignee FROM tasks").fetchall()
    for row in rows:
        people = [p.strip() for p in (row["assignee"] or "").split(",")]
        if old in people:
            updated = [new if p == old else p for p in people]
            # « Non attribué » n'a de sens que seul
            updated = [p for p in dict.fromkeys(updated) if p != UNASSIGNED] or [UNASSIGNED]
            conn.execute("UPDATE tasks SET assignee = ? WHERE id = ?", (", ".join(updated), row["id"]))


def resolve_assignee(raw):
    """Transforme le nom lu par le LLM en nom(s) de membre(s) du club (voir members.py)."""
    if names.is_unassigned(raw):
        return UNASSIGNED
    resolved = []
    for part in names.split_names(raw):
        if names.is_unassigned(part):
            continue
        known = list_members()
        member, exact = names.match_member(part, known)
        if member is None:
            member = create_member(part)
        elif not exact:
            display = names.clean_display(part)
            if display.lower() != member["name"].lower() and display not in member["aliases"]:
                update_member(member["id"], aliases=[*member["aliases"], display])
        resolved.append(member["name"])
    return ", ".join(dict.fromkeys(resolved)) or UNASSIGNED


# ---------- Réunions ----------

def create_meeting(title, meeting_date, language, source_type):
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO meetings (title, meeting_date, language, source_type, status, created_at)"
            " VALUES (?, ?, ?, ?, 'processing', ?)",
            (title, valid_date(meeting_date) or date.today().isoformat(), language, source_type, now()),
        )
    return cursor.lastrowid


def update_meeting(meeting_id, **fields):
    if "decisions" in fields:
        fields["decisions"] = json.dumps(fields["decisions"], ensure_ascii=False)
    columns = ", ".join(f"{key} = ?" for key in fields)
    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE meetings SET {columns} WHERE id = ?", (*fields.values(), meeting_id))
    if cursor.rowcount == 0:
        raise NotFound(f"Réunion {meeting_id} introuvable")


def get_meeting(meeting_id, with_content=True):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM meetings WHERE id = ?", (meeting_id,)).fetchone()
    if row is None:
        raise NotFound(f"Réunion {meeting_id} introuvable")
    meeting = dict(row)
    meeting["decisions"] = json.loads(meeting["decisions"] or "[]")
    meeting["tasks"] = list_tasks(meeting_id=meeting_id)
    if not with_content:
        meeting.pop("content", None)
    return meeting


def list_meetings():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT id, title, meeting_date, source_type, status FROM meetings ORDER BY meeting_date DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def delete_meeting(meeting_id):
    get_meeting(meeting_id, with_content=False)
    with get_connection() as conn:
        conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))


# ---------- Tâches ----------

def add_task(meeting_id, description, assignee=None, due_date=None, status="a_faire"):
    description = (description or "").strip()
    if not description:
        raise ValueError("La description est vide")
    if status not in TASK_STATUSES:
        raise ValueError(f"Statut invalide : {status}")
    if meeting_id:
        get_meeting(meeting_id, with_content=False)
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO tasks (meeting_id, description, assignee, due_date, status, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (meeting_id or None, description, resolve_assignee(assignee), valid_date(due_date), status, now()),
        )
    return get_task(cursor.lastrowid)


def _task_row(row, today):
    task = dict(row)
    task["overdue"] = bool(task["due_date"] and task["due_date"] < today and task["status"] != "termine")
    return task


def get_task(task_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT tasks.*, meetings.title AS meeting_title, meetings.meeting_date FROM tasks"
            " LEFT JOIN meetings ON meetings.id = tasks.meeting_id WHERE tasks.id = ?",
            (task_id,),
        ).fetchone()
    if row is None:
        raise NotFound(f"Tâche {task_id} introuvable")
    return _task_row(row, date.today().isoformat())


def list_tasks(meeting_id=None, status=None, assignee=None, overdue_only=False):
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
    # Les tâches sans échéance passent à la fin
    query += " ORDER BY tasks.due_date IS NULL, tasks.due_date, tasks.id"
    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    # Le retard est calculé à la lecture : rien à mettre à jour chaque jour
    today = date.today().isoformat()
    tasks = [_task_row(row, today) for row in rows]
    if assignee:
        tasks = [t for t in tasks if assignee.lower() in (p.strip().lower() for p in (t["assignee"] or "").split(","))]
    if overdue_only:
        tasks = [t for t in tasks if t["overdue"]]
    return tasks


def update_task(task_id, **fields):
    get_task(task_id)
    fields = {k: v for k, v in fields.items() if k in TASK_FIELDS}
    if "status" in fields and fields["status"] not in TASK_STATUSES:
        raise ValueError(f"Statut invalide : {fields['status']}")
    if "description" in fields and not (fields["description"] or "").strip():
        raise ValueError("La description est vide")
    if "assignee" in fields:
        fields["assignee"] = resolve_assignee(fields["assignee"])
    if "due_date" in fields:
        fields["due_date"] = valid_date(fields["due_date"])
    if fields:
        fields["updated_at"] = now()
        columns = ", ".join(f"{key} = ?" for key in fields)
        with get_connection() as conn:
            conn.execute(f"UPDATE tasks SET {columns} WHERE id = ?", (*fields.values(), task_id))
    return get_task(task_id)


def delete_task(task_id):
    task = get_task(task_id)
    with get_connection() as conn:
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return task


def get_stats():
    tasks = list_tasks()
    per_member = {}
    for task in tasks:
        for person in (p.strip() for p in (task["assignee"] or UNASSIGNED).split(",")):
            stats = per_member.setdefault(person, {"name": person, "total": 0, "done": 0, "overdue": 0})
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
        "members": sorted(per_member.values(), key=lambda m: (-m["total"], m["name"])),
        "upcoming": [t for t in tasks if t["status"] != "termine"][:5],
    }
