"""Client MCP : le backend lance le serveur MCP et lui parle via le protocole MCP (stdio).

Toutes les données RH (CV, postes, statuts) passent par ici.
"""
import json
import os
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import MCP_SERVER_SCRIPT


class MCPClient:
    def __init__(self):
        self.session = None
        self._stack = AsyncExitStack()

    async def start(self):
        params = StdioServerParameters(
            command=sys.executable,  # même Python que le backend
            args=[str(MCP_SERVER_SCRIPT)],
            cwd=str(MCP_SERVER_SCRIPT.parent),
            env=dict(os.environ),
        )
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()

    async def stop(self):
        await self._stack.aclose()

    async def list_tools(self):
        return (await self.session.list_tools()).tools

    async def call_raw(self, name, arguments=None):
        """Appelle un outil et renvoie le texte brut de sa réponse."""
        result = await self.session.call_tool(name, arguments or {})
        text = "".join(block.text for block in result.content if hasattr(block, "text"))
        if result.isError:
            raise RuntimeError(text or f"Erreur de l'outil {name}")
        return text

    async def call(self, name, arguments=None):
        """Appelle un outil et renvoie sa réponse JSON déjà décodée."""
        return json.loads(await self.call_raw(name, arguments))


mcp_client = MCPClient()
