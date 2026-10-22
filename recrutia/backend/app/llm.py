"""Appels au modèle de langage (Llama via l'API gratuite Groq)."""
import json

from groq import Groq

from .config import GROQ_API_KEY, GROQ_MODEL

_client = None


def get_client():
    global _client
    if not GROQ_API_KEY:
        raise RuntimeError("Clé GROQ_API_KEY manquante : ajoute-la dans backend/.env")
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def chat(messages, tools=None, json_mode=False, temperature=0.3):
    """Renvoie le message de réponse du modèle (avec d'éventuels appels d'outils)."""
    options = {}
    if tools:
        options["tools"] = tools
        options["tool_choice"] = "auto"
    if json_mode:
        options["response_format"] = {"type": "json_object"}
    response = get_client().chat.completions.create(
        model=GROQ_MODEL, messages=messages, temperature=temperature, **options
    )
    return response.choices[0].message


def ask(prompt, json_mode=False, temperature=0.3):
    content = chat([{"role": "user", "content": prompt}], json_mode=json_mode, temperature=temperature).content
    return json.loads(content) if json_mode else content
