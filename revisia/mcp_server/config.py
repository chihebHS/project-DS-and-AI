"""Configuration du serveur MCP (variables d'environnement)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

# Toutes les données vivent ici : SQLite (cours, chapitres) + index ChromaDB (+ graphe si pas de Neo4j).
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT_DIR / "data"))
DB_PATH = DATA_DIR / "revisia.db"
CHROMA_DIR = DATA_DIR / "chroma"

TOP_K = int(os.getenv("RAG_TOP_K", "4"))
# Similarité minimale entre un prérequis et une notion d'un chapitre précédent pour proposer un lien
LINK_MIN_SCORE = float(os.getenv("LINK_MIN_SCORE", "0.55"))

# Graphe de connaissances : Neo4j si NEO4J_URI est défini, sinon tables SQLite (même modèle de graphe)
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
MCP_HOST = os.getenv("MCP_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("MCP_PORT", "8765"))


def ensure_dirs():
    for folder in (DATA_DIR, CHROMA_DIR):
        folder.mkdir(parents=True, exist_ok=True)
