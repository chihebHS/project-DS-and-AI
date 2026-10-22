"""Appels au modèle de langage (Llama via l'API gratuite Groq)."""
import json

from groq import Groq

from ..config import GROQ_API_KEY, GROQ_MODEL, MAX_CHARS_FOR_GENERATION

_client = None

LANGUAGE_NAMES = {"fr": "français", "en": "anglais"}


def get_client():
    global _client
    if not GROQ_API_KEY:
        raise RuntimeError("Clé GROQ_API_KEY manquante : ajoute-la dans backend/.env")
    if _client is None:
        _client = Groq(api_key=GROQ_API_KEY)
    return _client


def ask_llm(messages, json_mode=False, temperature=0.3):
    options = {"response_format": {"type": "json_object"}} if json_mode else {}
    response = get_client().chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=temperature,
        **options,
    )
    return response.choices[0].message.content


def generate_study_material(text, language):
    """Génère en un seul appel : résumé, notions clés et quiz.

    Un seul appel au lieu de trois permet de rester dans les limites du plan gratuit.
    """
    lang = LANGUAGE_NAMES.get(language, "français")
    if len(text) > MAX_CHARS_FOR_GENERATION:
        text = text[:MAX_CHARS_FOR_GENERATION]

    prompt = f"""Tu es un assistant pédagogique. Voici le contenu d'un cours.
Réponds uniquement en {lang}, au format JSON suivant :
{{
  "summary": "résumé clair du cours en 10 à 15 lignes, avec des tirets pour les points importants",
  "key_concepts": [{{"term": "notion", "definition": "explication courte"}}],
  "quiz": [{{"question": "...", "choices": ["A", "B", "C", "D"], "answer_index": 0, "explanation": "..."}}]
}}
Donne entre 5 et 8 notions clés et exactement 5 questions à choix multiples.
Base-toi uniquement sur le contenu du cours.

CONTENU DU COURS :
{text}"""

    raw = ask_llm([{"role": "user", "content": prompt}], json_mode=True)
    data = json.loads(raw)
    return {
        "summary": data.get("summary", ""),
        "key_concepts": data.get("key_concepts", []),
        "quiz": data.get("quiz", []),
    }
