"""Test d'intégration du graphe sur une VRAIE base Neo4j (requêtes Cypher).

Ignoré par défaut. Lancé par Jenkins avec un conteneur neo4j:5, ou à la main :
    docker run -d -p 7687:7687 -e NEO4J_AUTH=neo4j/revisia-test neo4j:5.26-community
    NEO4J_TEST_URI=bolt://localhost:7687 NEO4J_TEST_PASSWORD=revisia-test pytest mcp_server/tests/test_neo4j_store.py
"""
import os

import pytest

from mcp_server.graph_store import Neo4jGraphStore, SqliteGraphStore

URI = os.getenv("NEO4J_TEST_URI")
pytestmark = pytest.mark.skipif(not URI, reason="NEO4J_TEST_URI non défini (pas de Neo4j disponible)")

COURSE = {"id": 1, "title": "Bases de données", "position": 1}
CHAPTERS = [
    {"id": 1, "position": 1, "title": "Modèle relationnel", "summary": "Tables",
     "concepts": [{"name": "Clé primaire", "definition": "Identifiant"}], "skills": ["Concevoir un schéma"],
     "prerequisites": []},
    {"id": 2, "position": 2, "title": "SELECT", "summary": "Requêtes",
     "concepts": [{"name": "Jointure", "definition": "Combiner"}], "skills": ["Écrire une requête"],
     "prerequisites": ["Clé primaire"]},
    {"id": 3, "position": 3, "title": "Agrégation", "summary": "GROUP BY",
     "concepts": [{"name": "GROUP BY"}], "skills": [], "prerequisites": ["Jointure"]},
]


def exercise(store):
    store.save_course_graph(COURSE, CHAPTERS)
    store.add_dependency(2, 1, "clés", ["Clé primaire"])
    store.add_dependency(3, 2, "jointures", ["Jointure"])
    knowledge = store.chapter_knowledge(2)
    result = {
        "stats": store.stats()["nodes"],
        "requires": [r["name"] for r in knowledge["requires"]],
        "depends_on": [(d["chapter_id"], d["reason"]) for d in knowledge["depends_on"]],
        "ancestors": store.ancestors(3),
        "covering": store.chapters_covering(["jointure"]),
        "subgraph": len(store.subgraph(1)["nodes"]),
    }
    store.delete_course_graph(1)
    result["after_delete"] = sum(store.stats()["nodes"].values())
    return result


@pytest.fixture
def neo4j_store():
    store = Neo4jGraphStore(URI, os.getenv("NEO4J_TEST_USER", "neo4j"), os.getenv("NEO4J_TEST_PASSWORD", ""))
    store.init()
    store._run("MATCH (n) DETACH DELETE n")
    yield store
    store._run("MATCH (n) DETACH DELETE n")
    store.close()


def test_neo4j_behaves_like_sqlite(neo4j_store, data_dir):
    from mcp_server.database import get_connection

    sqlite_store = SqliteGraphStore(get_connection)
    sqlite_store.init()
    expected = exercise(sqlite_store)
    assert exercise(neo4j_store) == expected
    assert expected["ancestors"] == {2: 1, 1: 2}  # chemin Cypher de longueur variable
