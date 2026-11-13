"""Test de bout en bout : API FastAPI → client MCP (stdio) → vrai serveur MCP → SQLite/ChromaDB.

Seul le LLM est simulé. Le serveur MCP tourne dans un sous-processus avec un dossier de données temporaire.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    from app.services import llm

    from .conftest import ScriptedChatModel

    llm.set_chat_model(ScriptedChatModel())
    with TestClient(app) as test_client:  # démarre le lifespan : lance le serveur MCP
        yield test_client
    llm.set_chat_model(None)


def test_health_and_readiness(client):
    health = client.get("/api/health").json()
    assert health["status"] == "ok" and health["mcp"]["connected"]
    assert client.get("/api/ready").status_code == 200
    tools = client.get("/api/mcp/tools").json()
    assert any(t["name"] == "update_task" and t["agent"] for t in tools)


def test_meeting_ingestion_end_to_end(client):
    assert client.post("/api/members", json={"name": "Karim"}).status_code == 201
    response = client.post("/api/meetings", data={
        "title": "Bureau robotique", "meeting_date": "2026-11-01", "language": "fr",
        "text": "Sarah réserve l'amphithéâtre. Karim prépare l'affiche. Budget de 300 euros validé."})
    assert response.status_code == 202
    meeting_id = response.json()["id"]

    # TestClient exécute la tâche de fond avant de rendre la main
    meeting = client.get(f"/api/meetings/{meeting_id}").json()
    assert meeting["status"] == "ready", meeting.get("error")
    assert meeting["decisions"] == ["Budget de 300 euros validé"]
    # Le LLM a écrit « Karim B. » : rattaché au membre connu Karim, et « Sarah » créée automatiquement
    assert {t["assignee"] for t in meeting["tasks"]} == {"Sarah", "Karim"}
    members = {m["name"]: m for m in client.get("/api/members").json()}
    assert members["Karim"]["aliases"] == ["Karim B."] and "Sarah" in members


def test_task_crud_and_errors(client):
    task = client.post("/api/tasks", json={"description": "Contacter les sponsors", "assignee": "Yasmine"}).json()
    assert task["assignee"] == "Yasmine"
    updated = client.patch(f"/api/tasks/{task['id']}", json={"status": "en_cours", "due_date": "2026-12-01"}).json()
    assert updated["status"] == "en_cours" and updated["due_date"] == "2026-12-01"
    cleared = client.patch(f"/api/tasks/{task['id']}", json={"due_date": None}).json()
    assert cleared["due_date"] is None

    assert client.patch("/api/tasks/9999", json={"status": "termine"}).status_code == 404
    assert client.patch(f"/api/tasks/{task['id']}", json={"status": "fini"}).status_code == 422
    assert client.post("/api/tasks", json={"description": "  "}).status_code == 400
    assert client.delete(f"/api/tasks/{task['id']}").status_code == 200
    assert client.get("/api/meetings/9999").status_code == 404


def test_members_merge(client):
    keep = client.post("/api/members", json={"name": "Amine"}).json()
    other = client.post("/api/members", json={"name": "Amine Kh"}).json()
    task = client.post("/api/tasks", json={"description": "Démo robot", "assignee": "Amine Kh"}).json()
    assert task["assignee"] == "Amine Kh"
    merged = client.post(f"/api/members/{keep['id']}/merge", json={"other_id": other["id"]}).json()
    assert "Amine Kh" in merged["aliases"]
    tasks = client.get("/api/tasks", params={"assignee": "Amine"}).json()
    assert [t["description"] for t in tasks] == ["Démo robot"]


def test_chat_with_rag_over_real_index(client):
    result = client.post("/api/chat", json={"question": "Qu'a-t-on décidé pour le budget ?"}).json()
    assert result["agents"] == ["historian"]
    assert result["sources"] and result["sources"][0]["title"] == "Bureau robotique"
    assert result["thread_id"]


def test_upload_validation(client):
    bad = client.post("/api/meetings", data={"title": "x"}, files={"file": ("cr.exe", b"MZ")})
    assert bad.status_code == 400
    assert client.post("/api/meetings", data={"title": "x"}).status_code == 400
    assert client.post("/api/meetings", data={"title": "x", "text": "a", "meeting_date": "32/13"}).status_code == 400
