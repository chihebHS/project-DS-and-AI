"""Client MCP du backend.

Toutes les données du club (réunions, tâches, membres, index RAG) passent par le serveur MCP.
Le backend garde UNE session MCP ouverte pendant toute sa vie :

- en local (MCP_TRANSPORT=stdio), il lance lui-même `python -m mcp_server` ;
- en Docker / Kubernetes (MCP_TRANSPORT=http), il se connecte au service MCP par son URL.

Deux usages :
- `await mcp.call("list_tasks", {...})` pour les routes REST et les nœuds déterministes ;
- `await mcp.langchain_tools([...])` pour donner des outils MCP aux agents LangGraph
  (conversion faite par langchain-mcp-adapters).
"""
import asyncio
import json
import logging
import os
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from .config import MCP_CONNECT_RETRIES, MCP_TRANSPORT, MCP_URL, ROOT_DIR

log = logging.getLogger("clubia.mcp_client")


class MCPToolError(Exception):
    """Erreur métier renvoyée par un outil MCP ({"error", "code"})."""

    def __init__(self, message, code=400):
        super().__init__(message)
        self.code = code


class _SessionProxy:
    """Les outils LangChain gardent ce proxy : après une reconnexion, ils utilisent la nouvelle session."""

    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        if self._client.session is None:
            raise RuntimeError("Session MCP non connectée")
        return getattr(self._client.session, name)


class MCPClient:
    def __init__(self, transport=MCP_TRANSPORT, url=MCP_URL, env=None):
        self.transport = transport
        self.url = url
        self.env = env
        self.session = None
        self._stack = None
        self._lock = asyncio.Lock()

    @property
    def connected(self):
        return self.session is not None

    async def _open(self):
        stack = AsyncExitStack()
        try:
            if self.transport == "stdio":
                params = StdioServerParameters(
                    command=sys.executable,  # même Python que le backend
                    args=["-m", "mcp_server"],
                    cwd=str(ROOT_DIR),
                    env={**os.environ, **(self.env or {}), "MCP_TRANSPORT": "stdio"},
                )
                read, write = await stack.enter_async_context(stdio_client(params))
            else:
                read, write, _ = await stack.enter_async_context(streamablehttp_client(self.url))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
        except BaseException:
            await stack.aclose()
            raise
        self._stack, self.session = stack, session

    async def start(self, retries=MCP_CONNECT_RETRIES):
        """Connexion avec nouvelles tentatives : en K8s, le serveur MCP peut démarrer après le backend."""
        delay = 1.0
        for attempt in range(1, retries + 1):
            try:
                await self._open()
                log.info("Connecté au serveur MCP (%s)", self.transport if self.transport == "stdio" else self.url)
                return
            except Exception as error:  # noqa: BLE001
                if attempt == retries:
                    raise
                log.warning("Serveur MCP indisponible (%s), nouvel essai dans %.0fs", error, delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 10)

    async def stop(self):
        if self._stack is not None:
            try:
                await self._stack.aclose()
            except Exception:  # noqa: BLE001 - fermeture best effort
                pass
        self._stack, self.session = None, None

    async def reconnect(self):
        async with self._lock:
            await self.stop()
            await self.start(retries=3)

    async def ping(self):
        if not self.session:
            return False
        try:
            await asyncio.wait_for(self.session.send_ping(), timeout=5)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def list_tools(self):
        return (await self.session.list_tools()).tools

    async def call_raw(self, name, arguments=None):
        """Appelle un outil et renvoie le texte de sa réponse. Reconnecte une fois si la session est perdue."""
        for attempt in (1, 2):
            try:
                if self.session is None:
                    raise ConnectionError("Session MCP non connectée")
                result = await self.session.call_tool(name, arguments or {})
                break
            except Exception as error:  # noqa: BLE001
                if attempt == 2:
                    raise
                log.warning("Appel MCP %s échoué (%s) : reconnexion", name, error)
                await self.reconnect()
        text = "".join(block.text for block in result.content if hasattr(block, "text"))
        if result.isError:
            raise MCPToolError(text or f"Erreur de l'outil {name}", 500)
        return text

    async def call(self, name, arguments=None):
        """Appelle un outil et renvoie sa réponse JSON décodée. Lève MCPToolError si l'outil signale une erreur."""
        data = json.loads(await self.call_raw(name, arguments))
        # Les erreurs des outils ont exactement la forme {"error", "code"} (une réunion a aussi un champ "error")
        if isinstance(data, dict) and set(data) == {"error", "code"}:
            raise MCPToolError(data["error"], data.get("code", 400))
        return data

    async def langchain_tools(self, names=None):
        """Outils MCP convertis en outils LangChain, filtrés par nom (liste blanche)."""
        from langchain_mcp_adapters.tools import load_mcp_tools

        tools = await load_mcp_tools(_SessionProxy(self))
        return [t for t in tools if names is None or t.name in names]


mcp = MCPClient()
