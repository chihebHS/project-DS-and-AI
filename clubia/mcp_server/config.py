"""Configuration du serveur MCP (variables d'environnement)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Toutes les données du club vivent ici : SQLite + index ChromaDB.
# En conteneur, ce dossier est un volume persistant (PVC Kubernetes).
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
DB_PATH = DATA_DIR / "club.db"
CHROMA_DIR = DATA_DIR / "chroma"

COLLECTION_NAME = os.getenv("CHROMA_COLLECTION", "meetings")
TOP_K = int(os.getenv("RAG_TOP_K", "4"))

TASK_STATUSES = ("a_faire", "en_cours", "termine")
UNASSIGNED = "Non attribué"

# Transport MCP : "stdio" (lancé par le backend en local) ou "streamable-http" (conteneur / K8s)
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8765"))


def ensure_dirs():
    for folder in (DATA_DIR, CHROMA_DIR):
        folder.mkdir(parents=True, exist_ok=True)
