"""Transcription d'un fichier audio avec Whisper (via l'API Groq)."""
from pathlib import Path

from ..config import WHISPER_MODEL
from .llm import get_client


def format_time(seconds):
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def transcribe_audio(path, language):
    """Retourne une liste de sections, une par minute environ, avec l'horodatage."""
    with open(path, "rb") as f:
        response = get_client().audio.transcriptions.create(
            file=(Path(path).name, f.read()),
            model=WHISPER_MODEL,
            language=language,
            response_format="verbose_json",
        )

    data = response.model_dump() if hasattr(response, "model_dump") else dict(response)
    segments = data.get("segments") or []
    if not segments:
        return [{"label": "audio", "text": data.get("text", "").strip()}]

    # On regroupe les petits segments de Whisper en blocs d'environ 60 secondes
    sections = []
    current_text, current_start = [], segments[0]["start"]
    for segment in segments:
        if segment["start"] - current_start >= 60 and current_text:
            sections.append({"label": f"à {format_time(current_start)}", "text": " ".join(current_text)})
            current_text, current_start = [], segment["start"]
        current_text.append(segment["text"].strip())
    if current_text:
        sections.append({"label": f"à {format_time(current_start)}", "text": " ".join(current_text)})
    return sections
