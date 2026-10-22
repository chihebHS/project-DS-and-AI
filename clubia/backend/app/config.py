"""Configuration de l'application (lue depuis le fichier .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Modèle de langage utilisé pour l'extraction et le chat
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Modèle de transcription audio (Whisper hébergé par Groq)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")

# Dossiers de stockage
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma"
DB_PATH = DATA_DIR / "club.db"

for folder in (DATA_DIR, UPLOAD_DIR, CHROMA_DIR):
    folder.mkdir(parents=True, exist_ok=True)

# Taille max du compte-rendu envoyé au LLM (limite du plan gratuit Groq)
MAX_CHARS_FOR_EXTRACTION = 15000
# Taille d'un morceau (chunk) de texte pour la recherche
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
# Nombre de passages récupérés pour répondre à une question
TOP_K = 4

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac"}
TEXT_EXTENSIONS = {".txt", ".md"}
PDF_EXTENSIONS = {".pdf"}

TASK_STATUSES = ("a_faire", "en_cours", "termine")
