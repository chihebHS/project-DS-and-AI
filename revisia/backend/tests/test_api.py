"""Bout en bout : API → client MCP (stdio) → vrai serveur MCP → SQLite + graphe + ChromaDB. Seul le LLM est simulé."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

SQL = ("Chapitre 1 : Modèle relationnel\n" + "Une table a une clé primaire. " * 8
       + "\nChapitre 2 : Requêtes SELECT\n" + "La requête select combine les tables. " * 8)
PANDAS = "Chapitre 1 : Pandas et SQL\n" + "On lit une base SQL avec pandas dans un DataFrame. " * 8


@pytest.fixture(scope="module")
def client():
    from app.services import llm

    from .conftest import ScriptedChatModel

    llm.set_chat_model(ScriptedChatModel())
    with TestClient(app) as test_client:
        yield test_client
    llm.set_chat_model(None)


def import_course(client, title, text):
    response = client.post("/api/courses", data={"title": title, "language": "fr", "text": text})
    assert response.status_code == 202
    course = client.get(f"/api/courses/{response.json()['id']}").json()  # la tâche de fond est terminée
    assert course["status"] == "ready", course.get("error")
    return course


def test_health(client):
    assert client.get("/api/health").json()["mcp"]["connected"]
    assert client.get("/api/ready").status_code == 200
    assert any(t["name"] == "learning_path" and t["agent"] for t in client.get("/api/mcp/tools").json())


def test_courses_graph_and_cross_course_prerequisites(client):
    sql = import_course(client, "Bases de données", SQL)
    pandas = import_course(client, "Python pour la data", PANDAS)
    ch1, ch2 = [c["id"] for c in sql["chapters"]]
    py1 = pandas["chapters"][0]["id"]

    # intra-cours : correspondance exacte → lien créé automatiquement
    assert [d["chapter_id"] for d in client.get(f"/api/chapters/{ch2}").json()["depends_on"]] == [ch1]
    # inter-cours : « Jointure » enseignée dans le chapitre 2 du cours précédent
    depends = client.get(f"/api/chapters/{py1}").json()["depends_on"]
    assert ch2 in [d["chapter_id"] for d in depends]

    path = client.get(f"/api/chapters/{py1}/path").json()
    assert [s["chapter_id"] for s in path["steps"]][-1] == py1 and path["steps"][0]["chapter_id"] == ch1

    graph = client.get("/api/graph", params={"course_id": pandas["id"]}).json()
    assert {f"course:{sql['id']}", f"chapter:{ch2}"} <= {n["uid"] for n in graph["nodes"]}
    only = client.get("/api/graph", params=[("types", "Course"), ("types", "Chapter")]).json()
    assert {n["type"] for n in only["nodes"]} == {"Course", "Chapter"}
    stats = client.get("/api/graph/stats").json()
    assert stats["backend"] == "sqlite" and stats["edges"]["DEPENDS_ON"] >= 2

    # une dépendance vers un chapitre suivant est refusée
    refused = client.post("/api/dependencies", json={"chapter_id": ch1, "prerequisite_chapter_id": ch2})
    assert refused.status_code == 400

    # réordonner le cursus supprime les liens devenus invalides
    moved = client.patch(f"/api/courses/{pandas['id']}/position", json={"position": 1}).json()
    assert moved["dependencies_removed"] >= 1
    assert client.get(f"/api/chapters/{py1}").json()["depends_on"] == []
    client.patch(f"/api/courses/{pandas['id']}/position", json={"position": 2})
    relinked = client.post(f"/api/courses/{pandas['id']}/relink").json()
    assert relinked["links"]


def test_chat_tutor_with_real_index(client):
    result = client.post("/api/chat", json={"question": "Explique la clé primaire"}).json()
    assert result["agents"] == ["tutor"] and result["sources"]


def test_errors(client):
    assert client.get("/api/courses/999").status_code == 404
    assert client.get("/api/chapters/999").status_code == 404
    assert client.post("/api/courses", data={"title": "x"}).status_code == 400
    assert client.post("/api/courses", data={"title": "x"}, files={"file": ("a.exe", b"MZ")}).status_code == 400
    assert client.patch("/api/courses/1/position", json={"position": 0}).status_code == 422
