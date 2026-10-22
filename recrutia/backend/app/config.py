"""Configuration du backend (lue depuis le fichier .env)."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(ROOT_DIR / "backend" / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

# Le script du serveur MCP, lancé par le backend comme un sous-processus
MCP_SERVER_SCRIPT = ROOT_DIR / "mcp_server" / "server.py"

# Outils MCP que l'agent conversationnel a le droit d'utiliser.
# Principe du moindre privilège : pas de suppression ni d'import de fichiers par le LLM.
AGENT_ALLOWED_TOOLS = {
    "list_candidates",
    "read_cv",
    "search_candidates",
    "update_candidate_status",
    "add_candidate_note",
    "list_jobs",
    "get_job",
    "pipeline_stats",
}

# Nombre max d'appels d'outils successifs pour une seule question
AGENT_MAX_STEPS = 6
# Taille max d'un résultat d'outil envoyé au LLM (limite du plan gratuit Groq)
MAX_TOOL_RESULT_CHARS = 5000
