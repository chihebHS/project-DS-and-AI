"""Agent conversationnel : le LLM décide lui-même quels outils MCP appeler.

Boucle :
1. On envoie au LLM la conversation + la liste des outils MCP autorisés.
2. S'il demande un outil, le backend l'exécute via MCP et renvoie le résultat au LLM.
3. On recommence jusqu'à ce que le LLM donne sa réponse finale.
"""
import json

from . import llm
from .config import AGENT_ALLOWED_TOOLS, AGENT_MAX_STEPS, MAX_TOOL_RESULT_CHARS
from .mcp_client import mcp_client

SYSTEM_PROMPT = """Tu es RecrutIA, un assistant pour les recruteurs.
Tu n'as accès aux CV et au suivi des candidats QUE par les outils fournis.
- Pour trouver des profils, utilise search_candidates, puis read_cv pour vérifier les détails.
- N'invente jamais d'information sur un candidat : appuie-toi sur ce que renvoient les outils.
- Cite les candidats avec leur nom et leur id, par exemple « Sarah Benali (id 3) ».
- Avant de changer un statut, vérifie que la demande du recruteur est claire.
Réponds en français, de façon concise et structurée."""


async def get_llm_tools():
    """Convertit les outils MCP au format « function calling » attendu par le LLM."""
    tools = []
    for tool in await mcp_client.list_tools():
        if tool.name in AGENT_ALLOWED_TOOLS:
            tools.append({
                "type": "function",
                "function": {"name": tool.name, "description": tool.description, "parameters": tool.inputSchema},
            })
    return tools


async def run_agent(history):
    """history : liste de messages {role: user|assistant, content: str}."""
    tools = await get_llm_tools()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    steps = []  # trace des outils appelés, affichée dans l'interface

    for _ in range(AGENT_MAX_STEPS):
        reply = llm.chat(messages, tools=tools, temperature=0.2)

        if not reply.tool_calls:
            return {"answer": reply.content, "steps": steps}

        messages.append({
            "role": "assistant",
            "content": reply.content or "",
            "tool_calls": [
                {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                for c in reply.tool_calls
            ],
        })

        for call in reply.tool_calls:
            name = call.function.name
            arguments = {}
            try:
                arguments = json.loads(call.function.arguments or "{}")
                if name not in AGENT_ALLOWED_TOOLS:
                    raise PermissionError(f"Outil non autorisé : {name}")
                result = await mcp_client.call_raw(name, arguments)
            except Exception as error:
                # L'erreur est renvoyée au LLM, qui peut corriger son appel
                result = json.dumps({"error": str(error)}, ensure_ascii=False)

            steps.append({"tool": name, "arguments": arguments, "result": result[:400]})
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result[:MAX_TOOL_RESULT_CHARS]})

    return {"answer": "Je n'ai pas réussi à terminer en un nombre raisonnable d'étapes. Reformule ta demande.", "steps": steps}
