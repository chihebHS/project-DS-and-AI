"""Tests des outils MCP via le protocole (session en mémoire) et de l'index RAG."""
import json

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_server import rag
from mcp_server.server import mcp


async def call(session, name, args=None):
    result = await session.call_tool(name, args or {})
    return json.loads(result.content[0].text)


async def test_tools_over_mcp_protocol(data_dir):
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        assert {"search_meetings", "list_tasks", "update_task", "complete_meeting"} <= names

        meeting = await call(session, "create_meeting", {"title": "Bureau", "meeting_date": "2026-11-01"})
        await call(session, "complete_meeting", {
            "meeting_id": meeting["id"], "content": "texte", "summary": "Résumé", "decisions": ["Gala"],
            "tasks": [{"description": "Affiche", "assignee": "Karim", "due_date": "2026-11-10"},
                      {"description": "", "assignee": "Personne"}],
        })
        tasks = await call(session, "list_tasks", {"meeting_id": meeting["id"]})
        assert len(tasks) == 1 and tasks[0]["assignee"] == "Karim"

        updated = await call(session, "update_task", {"task_id": tasks[0]["id"], "status": "termine"})
        assert updated["status"] == "termine"

        error = await call(session, "update_task", {"task_id": 999, "status": "termine"})
        assert error["code"] == 404

        prompt = await session.get_prompt("weekly_report", {"language": "fr"})
        assert "get_stats" in prompt.messages[0].content.text


def test_rag_index_and_search(data_dir):
    rag.index_meeting(1, "Bureau robotique", "2026-11-01", [
        {"label": "page 1", "text": "Le budget de 300 euros pour la journée portes ouvertes a été validé."},
        {"label": "page 2", "text": "Amine s'occupe de la démonstration du robot devant les visiteurs."},
    ])
    passages = rag.search("démonstration du robot", k=1)
    assert passages[0]["label"] == "page 2" and passages[0]["meeting_id"] == 1
    rag.remove_meeting(1)
    assert rag.search("robot") == []
