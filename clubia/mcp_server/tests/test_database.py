from datetime import date, timedelta

import pytest

from mcp_server import database as db

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


def test_meeting_lifecycle(data_dir):
    meeting_id = db.create_meeting("Bureau", "2026-11-01", "fr", "saisie")
    assert db.get_meeting(meeting_id)["status"] == "processing"
    db.update_meeting(meeting_id, summary="Résumé", decisions=["Gala validé"], status="ready")
    meeting = db.get_meeting(meeting_id)
    assert meeting["decisions"] == ["Gala validé"] and meeting["status"] == "ready"
    db.delete_meeting(meeting_id)
    with pytest.raises(db.NotFound):
        db.get_meeting(meeting_id)


def test_tasks_are_cascaded_with_meeting(data_dir):
    meeting_id = db.create_meeting("Bureau", "2026-11-01", "fr", "saisie")
    task = db.add_task(meeting_id, "Réserver la salle", "Sarah", TOMORROW)
    db.delete_meeting(meeting_id)
    with pytest.raises(db.NotFound):
        db.get_task(task["id"])


def test_assignee_normalization_creates_and_reuses_members(data_dir):
    db.add_task(None, "Affiche", "Karim", None)
    task = db.add_task(None, "Instagram", "Karim B.", None)
    assert task["assignee"] == "Karim"
    members = db.list_members()
    assert [m["name"] for m in members] == ["Karim"]
    assert members[0]["aliases"] == ["Karim B."]


def test_multiple_assignees_and_stats_split(data_dir):
    db.add_task(None, "Stand", "Sarah et Karim", YESTERDAY)
    stats = db.get_stats()
    names = {m["name"]: m for m in stats["members"]}
    assert set(names) == {"Sarah", "Karim"}
    assert names["Sarah"]["overdue"] == 1 and stats["tasks_overdue"] == 1


def test_overdue_is_computed_on_read(data_dir):
    late = db.add_task(None, "En retard", "Amine", YESTERDAY)
    done = db.add_task(None, "Fini", "Amine", YESTERDAY, status="termine")
    assert late["overdue"] and not done["overdue"]
    assert [t["id"] for t in db.list_tasks(overdue_only=True)] == [late["id"]]


def test_update_task_validates(data_dir):
    task = db.add_task(None, "Budget", "", "pas une date")
    assert task["assignee"] == "Non attribué" and task["due_date"] is None
    with pytest.raises(ValueError):
        db.update_task(task["id"], status="fini")
    updated = db.update_task(task["id"], status="en_cours", due_date=TOMORROW)
    assert updated["status"] == "en_cours" and updated["due_date"] == TOMORROW
    with pytest.raises(db.NotFound):
        db.update_task(9999, status="termine")


def test_merge_members_moves_tasks_and_aliases(data_dir):
    task = db.add_task(None, "Sponsoring", "Yasmine", None)
    keep = db.list_members()[0]
    other = db.create_member("Yas")
    db.update_task(task["id"], assignee="Yas")
    merged = db.merge_members(keep["id"], other["id"])
    assert "Yas" in merged["aliases"]
    assert db.get_task(task["id"])["assignee"] == "Yasmine"


def test_rename_member_updates_tasks(data_dir):
    task = db.add_task(None, "Démo robot", "Amine", None)
    member = db.list_members()[0]
    db.update_member(member["id"], name="Amine K.")
    assert db.get_task(task["id"])["assignee"] == "Amine K."


def test_delete_member_unassigns_tasks(data_dir):
    task = db.add_task(None, "Démo robot", "Amine", None)
    db.delete_member(db.list_members()[0]["id"])
    assert db.get_task(task["id"])["assignee"] == "Non attribué"
