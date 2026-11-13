"""Configuration du backend (fichier .env en local, variables d'environnement en conteneur)."""
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent  # revisia/backend
ROOT_DIR = BASE_DIR.parent  # revisia
load_dotenv(BASE_DIR / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_ROUTER_MODEL = os.getenv("GROQ_ROUTER_MODEL", GROQ_MODEL)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-large-v3-turbo")

# ---------- Serveur MCP ----------
# "stdio" : le backend lance lui-même `python -m mcp_server` (développement local)
# "http"  : le serveur MCP tourne à part (Docker Compose, Kubernetes)
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8765/mcp")
MCP_CONNECT_RETRIES = int(os.getenv("MCP_CONNECT_RETRIES", "10"))

# ---------- Stockage propre au backend ----------
STATE_DIR = Path(os.getenv("STATE_DIR", BASE_DIR / "state"))
CHECKPOINT_DB = os.getenv("CHECKPOINT_DB", str(STATE_DIR / "checkpoints.db"))
UPLOAD_TMP_DIR = Path(os.getenv("UPLOAD_TMP_DIR", tempfile.gettempdir())) / "revisia-uploads"

CORS_ORIGINS = [o.strip() for o in os.getenv(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ---------- Traitement des cours ----------
MAX_CHARS_PER_CHAPTER = int(os.getenv("MAX_CHARS_PER_CHAPTER", "12000"))
MAX_CHAPTERS = int(os.getenv("MAX_CHAPTERS", "15"))
MAX_CHARS_PER_PART = MAX_CHARS_PER_CHAPTER  # découpage par taille quand le cours n'a pas de titres
PART_OVERLAP = 300
CHUNK_SIZE = 800
CHUNK_OVERLAP = 150
TOP_K = int(os.getenv("RAG_TOP_K", "4"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "25"))
MAX_AGENT_STEPS = int(os.getenv("MAX_AGENT_STEPS", "8"))
# Un lien sémantique est accepté sans validation du LLM au-dessus de ce score (repli si le LLM échoue)
AUTO_LINK_SCORE = float(os.getenv("AUTO_LINK_SCORE", "0.8"))

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".webm", ".flac"}
TEXT_EXTENSIONS = {".txt", ".md"}
PDF_EXTENSIONS = {".pdf"}

for folder in (STATE_DIR, UPLOAD_TMP_DIR):
    folder.mkdir(parents=True, exist_ok=True)
