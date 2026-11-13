"""Outils de test du backend : faux LLM scripté et faux client MCP. Aucun appel réseau."""
import json
import os
import re
import tempfile

# Avant tout import de `app` : données isolées, mémoire volatile, clé factice
_TMP = tempfile.mkdtemp(prefix="revisia-tests-")
os.environ.update({"DATA_DIR": _TMP, "STATE_DIR": _TMP, "CHECKPOINT_DB": "", "GROQ_API_KEY": "test-key",
                   "MCP_TRANSPORT": "stdio", "MCP_CONNECT_RETRIES": "2", "NEO4J_URI": ""})

import pytest  # noqa: E402
from langchain_core.language_models.chat_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402

from app.services import llm  # noqa: E402

# Ce que le faux LLM « comprend » de chaque chapitre, selon un mot présent dans le texte
CHAPTER_KNOWLEDGE = {
    "relationnel": {"concepts": [{"name": "Clé primaire", "definition": "Identifiant unique d'une ligne"},
                                 {"name": "Table", "definition": "Lignes et colonnes"}],
                    "skills": ["Concevoir un schéma"], "prerequisites": []},
    "select": {"concepts": [{"name": "Jointure", "definition": "Combiner deux tables"}],
               "skills": ["Écrire une requête SQL"], "prerequisites": ["Clé primaire", "Table"]},
    "pandas": {"concepts": [{"name": "DataFrame", "definition": "Tableau pandas"}],
               "skills": ["Charger des données SQL"], "prerequisites": ["Jointure", "Identifiant unique d'une ligne"]},
}
QUIZ = [{"question": "Qu'est-ce qu'une clé primaire ?", "choices": ["Un identifiant", "Une table", "Un index", "Rien"],
         "answer_index": 0, "explanation": "Elle identifie une ligne."}]


class ScriptedChatModel(BaseChatModel):
    """Faux modèle de chat : choisit sa réponse d'après le contenu du prompt."""

    calls: list = []
    validate_links: bool = True

    @property
    def _llm_type(self):
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def respond(self, messages):
        text = "\n".join(str(m.content) for m in messages)
        last = messages[-1]
        if isinstance(messages[0], SystemMessage) and "conseiller pédagogique" in str(messages[0].content):
            if isinstance(last, ToolMessage):
                return AIMessage(f"Parcours : {last.content[:80]}")
            return AIMessage("", tool_calls=[{"name": "list_chapters", "args": {}, "id": "call-1"}])
        if "Plusieurs agents ont répondu" in text:
            return AIMessage("Synthèse finale [1].")
        if "ingénieur pédagogique" in text:
            chapter_text = text.split("TEXTE DU CHAPITRE :")[-1].lower()
            key = next((k for k in CHAPTER_KNOWLEDGE if k in chapter_text), "relationnel")
            title = re.search(r"chapitre (\d+)/", text).group(1)
            return AIMessage(json.dumps({"title": f"Titre LLM {title}", "summary": f"Résumé {key}",
                                         **CHAPTER_KNOWLEDGE[key]}, ensure_ascii=False))
        if "résumés des chapitres du cours" in text:
            return AIMessage(json.dumps({"summary": "Résumé du cours", "key_concepts": [
                {"term": "Clé primaire", "definition": "Identifiant"}], "quiz": QUIZ}, ensure_ascii=False))
        if "graphe des prérequis" in text:
            if not self.validate_links:
                return AIMessage("pas du JSON")
            pairs = re.findall(r"CHAPITRE (\d+).*?\n((?:  - candidat .*\n?)+)", text)
            links = [{"chapter_id": int(cid), "prerequisite_chapter_id": int(pid), "reason": "validé"}
                     for cid, block in pairs for pid in re.findall(r"candidat (\d+)", block)]
            return AIMessage(json.dumps({"links": links}))
        if "superviseur" in text:
            question = text.split("Dernier message :")[-1].lower()
            agents = []
            if "explique" in question:
                agents.append("tutor")
            if "prérequis" in question:
                agents.append("navigator")
            if "quiz" in question:
                agents.append("quizmaster")
            return AIMessage(json.dumps({"agents": agents, "reasoning": "test"}))
        if "Réécris la dernière question" in text:
            return AIMessage("Question reformulée")
        if "tuteur patient" in text:
            return AIMessage("Une clé primaire identifie une ligne [1].")
        if "examinateur" in text:
            return AIMessage(json.dumps({"quiz": QUIZ * 3}, ensure_ascii=False))
        if isinstance(last, HumanMessage):
            return AIMessage("Bonjour, je suis RevisIA.")
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
