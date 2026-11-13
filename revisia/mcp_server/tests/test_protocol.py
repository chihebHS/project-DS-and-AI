"""Les outils sont bien exposés et utilisables via le protocole MCP (session en mémoire)."""
import json

from mcp.shared.memory import create_connected_server_and_client_session

from mcp_server.server import mcp


async def test_tools_over_mcp_protocol(data_dir):
    async with create_connected_server_and_client_session(mcp._mcp_server) as session:
        names = {t.name for t in (await session.list_tools()).tools}
        assert {"search_courses", "learning_path", "get_knowledge_graph", "add_dependency"} <= names

        created = json.loads((await session.call_tool("create_course", {"title": "Réseaux"})).content[0].text)
        indexed = await session.call_tool("index_course", {"course_id": created["id"], "chunks": [
            {"label": "page 1", "text": "Le modèle OSI comporte sept couches, de la couche physique à l'application."}]})
        assert json.loads(indexed.content[0].text)["indexed"] == 1
        hits = json.loads((await session.call_tool("search_courses", {"query": "couches OSI"})).content[0].text)
        assert hits[0]["label"] == "page 1" and hits[0]["title"] == "Réseaux"

        missing = json.loads((await session.call_tool("get_chapter", {"chapter_id": 999})).content[0].text)
        assert missing["code"] == 404

        prompt = await session.get_prompt("revision_plan", {"chapter_title": "OSI"})
        assert "learning_path" in prompt.messages[0].content.text
