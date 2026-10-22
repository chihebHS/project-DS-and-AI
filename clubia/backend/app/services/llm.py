"""Appels au modèle de langage (Llama via l'API gratuite Groq)."""
import json

from groq import Groq

from ..config import GROQ_API_KEY, GROQ_MODEL, MAX_CHARS_FOR_EXTRACTION

_client = None

LANGUAGE_NAMES = {"fr": "français", "en": "anglais"}


def get_client():
    global _client
    if not GROQ_API_KEY:
        raise RuntimeError("Clé GROQ_API_KEY manquante : ajoute-la dans backend/.env")
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def ask_llm(messages, json_mode=False, temperature=0.2):
    options = {"response_format": {"type": "json_object"}} if json_mode else {}
    response = get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=temperature,
        **options,
    )
    return response.choices[0].message.content


def extract_meeting_info(text, meeting_date, language):
    """Extrait d'un compte-rendu : le résumé, les décisions et les tâches à faire."""
    lang = LANGUAGE_NAMES.get(language, "français")
    if len(text) > MAX_CHARS_FOR_EXTRACTION:
        text = text[:MAX_CHARS_FOR_EXTRACTION]

    prompt = f"""Tu es le secrétaire d'un club étudiant. Voici le compte-rendu d'une réunion du {meeting_date}.
Réponds uniquement en {lang}, au format JSON suivant :
{{
  "summary": "résumé de la réunion en 5 à 10 lignes",
  "decisions": ["décision prise pendant la réunion"],
  "tasks": [{{"description": "ce qu'il faut faire", "assignee": "personne responsable", "due_date": "AAAA-MM-JJ"}}]
}}
Règles :
- "decisions" contient seulement ce qui a été décidé ou validé.
- "tasks" contient les actions concrètes à réaliser après la réunion.
- "assignee" : le prénom (ou nom) de la personne responsable, ou "Non attribué" si personne n'est cité.
- "due_date" : la date limite au format AAAA-MM-JJ. Si elle est relative ("vendredi prochain",
  "dans deux semaines"), calcule-la à partir de la date de la réunion ({meeting_date}). Mets null si aucune date.
- N'invente rien qui n'est pas dans le compte-rendu.

COMPTE-RENDU :
{text}"""

    data = json.loads(ask_llm([{"role": "user", "content": prompt}], json_mode=True))
    return {
        "summary": data.get("summary", ""),
        "decisions": data.get("decisions", []),
        "tasks": data.get("tasks", []),
    }
