"""Configuration du backend (fichier .env en local, variables d'environnement en conteneur)."""
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # clubia/backend
ROOT_DIR = BASE_DIR.parent  # clubia
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
# Modèle plus léger pour le routage du superviseur (rapide et économe en jetons)
GROQ_ROUTER_MODEL = os.getenv("GROQ_ROUTER_MODEL", GROQ_MODEL)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")

# ---------- Serveur MCP ----------
# "stdio" : le backend lance lui-même `python -m mcp_server` (développement local)
# "http"  : le serveur MCP tourne à part (Docker Compose, Kubernetes) et on s'y connecte par URL
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8765/mcp")
MCP_CONNECT_RETRIES = int(os.getenv("MCP_CONNECT_RETRIES", "10"))

# ---------- Stockage propre au backend ----------
# Mémoire des conversations (checkpoints LangGraph). Vide = mémoire volatile.
STATE_DIR = Path(os.getenv("STATE_DIR", BASE_DIR / "state"))
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", str(STATE_DIR / "checkpoints.db"))
UPLOAD_TMP_DIR = Path(os.getenv("UPLOAD_TMP_DIR", tempfile.gettempdir())) / "clubia-uploads"

CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5174,http://127.0.0.1:5174").split(",") if o.strip()]
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ---------- Traitement des comptes-rendus ----------
# Au-delà, le texte est découpé en parties analysées en parallèle (map-reduce LangGraph)
MAX_CHARS_PER_PART = int(os.getenv("MAX_CHARS_PER_PART", "12000"))
PART_OVERLAP = 500
CHUNK_SIZE = 800  # morceaux pour l'index de recherche
CHUNK_OVERLAP = 150
TOP_K = int(os.getenv("RAG_TOP_K", "4"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
# Nombre maximum d'appels d'outils de l'agent des tâches par question
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "8"))

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac"}
TEXT_EXTENSIONS = {".txt", ".md"}
PDF_EXTENSIONS = {".pdf"}

TASK_STATUSES = ("a_faire", "en_cours", "termine")

for folder in (STATE_DIR, UPLOAD_TMP_DIR):
    folder.mkdir(parents=True, exist_ok=True)
