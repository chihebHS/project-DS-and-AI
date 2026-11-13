"""Accès aux modèles : Llama 3.3 via Groq, à travers LangChain (ChatGroq).

- `get_chat_model()` : le modèle de chat utilisé par les agents LangGraph.
- `ainvoke_json()` : appel en mode JSON validé par un schéma Pydantic (extraction, routage).
- `get_groq_client()` : client Groq brut, pour Whisper (transcription audio).

Les tests remplacent le modèle par un faux avec `set_chat_model()` : aucun appel réseau.
"""
import json
import re

from ..config import GROQ_API_KEY, GROQ_MODEL, GROQ_ROUTER_MODEL

LANGUAGE_NAMES = {"fr": "français", "en": "anglais"}


class LLMNotConfigured(RuntimeError):
    pass


_models = {}
_override = None
_groq_client = None


def _require_key():
    if not GROQ_API_KEY:
        raise LLMNotConfigured("Clé GROQ_API_KEY manquante : ajoute-la dans backend/.env")


def get_chat_model(role="main"):
    """role = "main" (réponses, extraction) ou "router" (décisions rapides du superviseur)."""
    if _override is not None:
        return _override
    _require_key()
    if role not in _models:
        from langchain_groq import ChatGroq

        model = GROQ_ROUTER_MODEL if role == "router" else GROQ_MODEL
        _models[role] = ChatGroq(model=model, api_key=GROQ_API_KEY, temperature=0.2, max_retries=2)
    return _models[role]


def set_chat_model(model):
    """Injecte un modèle (tests). None revient au vrai modèle Groq."""
    global _override
    _override = model


def get_groq_client():
    global _groq_client
    _require_key()
    if _groq_client is None:
        from groq import Groq

        _groq_client = Groq(api_key=GROQ_API_KEY)
    return _groq_client


def extract_json(text):
    """Récupère l'objet JSON d'une réponse, même entouré de texte ou de ```json."""
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


async def ainvoke_json(messages, schema, role="main"):
    """Appelle le LLM en mode JSON et valide la réponse avec le schéma Pydantic `schema`.

    Une réponse invalide lève une exception : le nœud LangGraph qui appelle cette fonction
    a une RetryPolicy, l'appel est donc retenté automatiquement.
    """
    model = get_chat_model(role).bind(response_format={"type": "json_object"})
    response = await model.ainvoke(messages)
    return schema.model_validate(extract_json(response.content))


async def ainvoke_text(messages, role="main"):
    response = await get_chat_model(role).ainvoke(messages)
    return response.content.strip()
