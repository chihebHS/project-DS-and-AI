import json

import pytest

from mcp_server import config, database, graph_store


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Chaque test a sa propre base SQLite, son propre graphe et son propre index ChromaDB."""
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "revisia.db")
    monkeypatch.setattr(config, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr(config, "NEO4J_URI", "")
    graph_store.reset_store()
    database.init_db()
    yield tmp_path
    graph_store.reset_store()


def call(tool, **kwargs):
    """Appelle un outil du serveur comme le ferait un client MCP (réponse JSON décodée)."""
    return json.loads(tool(**kwargs))


SQL_CHAPTERS = [
    {"title": "Modèle relationnel", "summary": "Tables et clés.",
     "concepts": [{"name": "Clé primaire", "definition": "Identifiant unique d'une ligne d'une table"},
                  {"name": "Table", "definition": "Ensemble de lignes et de colonnes"}],
     "skills": ["Concevoir un schéma relationnel"], "prerequisites": []},
    {"title": "Requêtes SELECT", "summary": "Interroger les tables.",
     "concepts": [{"name": "Jointure", "definition": "Combiner les lignes de deux tables"}],
     "skills": ["Écrire une requête SQL"], "prerequisites": ["Clé primaire", "Table"]},
]

PYTHON_DATA_CHAPTERS = [
    {"title": "Pandas et bases de données", "summary": "Lire une base SQL avec pandas.",
     "concepts": [{"name": "DataFrame", "definition": "Tableau de données pandas"}],
     "skills": ["Charger des données SQL dans pandas"],
     "prerequisites": ["Jointure SQL", "Identifiant unique d'une ligne"]},
]
