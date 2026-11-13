"""Outils de test du backend : faux LLM scripté et faux client MCP.

Aucun appel réseau : le faux LLM répond selon le prompt reçu (les agents tournent en parallèle,
on ne peut donc pas se fier à l'ordre des appels).
"""
import json
import os
import tempfile

# Avant tout import de `app` : données isolées, mémoire volatile, clé factice
_TMP = tempfile.mkdtemp(prefix="clubia-tests-")
os.environ.update({"DATA_DIR": _TMP, "STATE_DIR": _TMP, "CHECKPOINT_DB": "", "GROQ_API_KEY": "test-key",
                   "MCP_TRANSPORT": "stdio", "MCP_CONNECT_RETRIES": "2"})

import pytest  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from app.services import llm  # noqa: E402

EXTRACTION = {
    "summary": "Le club prépare une journée portes ouvertes.",
    "decisions": ["Budget de 300 euros validé"],
    "tasks": [
        {"description": "Réserver l'amphithéâtre", "assignee": "Sarah", "due_date": "2026-11-07"},
        {"description": "Préparer l'affiche", "assignee": "Karim B.", "due_date": "date floue"},
        {"description": "Réserver l'amphithéâtre", "assignee": "Sarah", "due_date": "2026-11-07"},
    ],
}


class ScriptedChatModel(BaseChatModel):
    """Faux modèle de chat : choisit sa réponse d'après le contenu du prompt."""

    calls: list = []

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def respond(self, messages):
        text = "\n".join(str(m.content) for m in messages)
        last = messages[-1]
        if isinstance(messages[0], SystemMessage) and "gestionnaire des tâches" in str(messages[0].content):
            if isinstance(last, ToolMessage):
                return AIMessage(f"Tâches trouvées : {last.content[:80]}")
            return AIMessage("", tool_calls=[{"name": "list_tasks", "args": {"assignee": "Karim"}, "id": "call-1"}])
        if "Plusieurs agents spécialisés" in text:
            return AIMessage("Synthèse finale [1].")
        if "secrétaire d'un club" in text:
            return AIMessage(json.dumps(EXTRACTION, ensure_ascii=False))
        if "Fusionne-les" in text:
            return AIMessage(json.dumps({"summary": "Résumé fusionné", "decisions": ["D1", "D2"]}))
        if "superviseur" in text:
            question = text.split("Dernier message :")[-1].lower()
            agents = []
            if "décid" in question:
                agents.append("historian")
            if "tâche" in question:
                agents.append("task_manager")
            if "bilan" in question:
                agents.append("analyst")
            return AIMessage(json.dumps({"agents": agents, "reasoning": "test"}))
        if "Réécris la dernière question" in text:
            return AIMessage("Question reformulée")
        if "archiviste" in text:
            return AIMessage("Le budget de 300 euros a été validé [1].")
        if "analyste" in text:
            return AIMessage("Bilan : 1 tâche en retard.")
        if isinstance(last, HumanMessage):
            return AIMessage("Bonjour, je suis ClubIA.")
        return AIMessage("ok")

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls.append(messages)
        return ChatResult(generations=[ChatGeneration(message=self.respond(messages))])


@pytest.fixture
def fake_llm():
    model = ScriptedChatModel()
    model.calls = []
    llm.set_chat_model(model)
    yield model
    llm.set_chat_model(None)


class FakeMCP:
    """Faux client MCP : enregistre les appels et renvoie des réponses prévues."""

    transport = "fake"
    connected = True

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or {}

    async def call(self, name, arguments=None):
        self.calls.append((name, arguments or {}))
        response = self.responses.get(name, {})
        if isinstance(response, Exception):
            raise response
        return response(arguments or {}) if callable(response) else response

    def names(self):
        return [name for name, _ in self.calls]
