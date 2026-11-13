"""Tests du graphe de connaissances et des règles de dépendance (seulement vers un chapitre précédent)."""
from mcp_server import server
from mcp_server.graph_store import slug

from .conftest import PYTHON_DATA_CHAPTERS, SQL_CHAPTERS, call


def add_course(title, chapters):
    course_id = call(server.create_course, title=title)["id"]
    saved = call(server.save_course_analysis, course_id=course_id, content="texte", summary="résumé",
                 key_concepts=[], quiz=[], chapters=chapters)
    return course_id, [c["id"] for c in saved["chapters"]]


def test_slug_merges_spellings():
    assert slug("La clé primaire") == slug("clé primaire") == "cle-primaire"
    assert slug("SQL (Structured Query Language)") == "sql"


def test_course_graph_structure(data_dir):
    course_id, (ch1, ch2) = add_course("Bases de données", SQL_CHAPTERS)
    stats = call(server.graph_stats)
    assert stats["backend"] == "sqlite"
    assert stats["nodes"] == {"Course": 1, "Chapter": 2, "Concept": 3, "Skill": 2}
    assert stats["edges"]["HAS_CHAPTER"] == 2 and stats["edges"]["NEXT"] == 1
    assert stats["edges"]["REQUIRES"] == 2

    chapter = call(server.get_chapter, chapter_id=ch2)
    assert [c["name"] for c in chapter["covers"]] == ["Jointure"]
    assert [s["name"] for s in chapter["teaches"]] == ["Écrire une requête SQL"]
    assert {r["name"] for r in chapter["requires"]} == {"Clé primaire", "Table"}
    # le prérequis réutilise le nœud déjà enseigné (même notion, avec sa définition)
    assert any(r["definition"] for r in chapter["requires"])


def test_candidates_only_from_preceding_chapters(data_dir):
    _, (ch1, ch2) = add_course("Bases de données", SQL_CHAPTERS)
    _, (py1,) = add_course("Python pour la data", PYTHON_DATA_CHAPTERS)

    exact = call(server.find_prerequisite_candidates, chapter_id=ch2)
    assert [c["chapter_id"] for c in exact] == [ch1]
    assert {m["method"] for m in exact[0]["matches"]} == {"exact"} and exact[0]["same_course"]

    # formulés autrement : retrouvés par similarité sémantique, dans un cours PRÉCÉDENT
    semantic = call(server.find_prerequisite_candidates, chapter_id=py1)
    found = {c["chapter_id"] for c in semantic}
    assert found <= {ch1, ch2} and found
    assert all(not c["same_course"] for c in semantic)

    # le premier chapitre ne peut dépendre de rien
    assert call(server.find_prerequisite_candidates, chapter_id=ch1) == []


def test_dependency_must_point_backwards(data_dir):
    _, (ch1, ch2) = add_course("Bases de données", SQL_CHAPTERS)
    assert call(server.add_dependency, chapter_id=ch2, prerequisite_chapter_id=ch1, reason="clés")["depends_on"] == ch1
    refused = call(server.add_dependency, chapter_id=ch1, prerequisite_chapter_id=ch2)
    assert refused["code"] == 400
    assert call(server.get_chapter, chapter_id=ch1)["required_by"][0]["chapter_id"] == ch2


def test_learning_path_is_transitive_and_ordered(data_dir):
    _, (ch1, ch2) = add_course("Bases de données", SQL_CHAPTERS)
    _, (py1,) = add_course("Python pour la data", PYTHON_DATA_CHAPTERS)
    call(server.add_dependency, chapter_id=ch2, prerequisite_chapter_id=ch1, concepts=["Clé primaire"])
    call(server.add_dependency, chapter_id=py1, prerequisite_chapter_id=ch2, concepts=["Jointure"])

    path = call(server.learning_path, chapter_id=py1)
    assert [s["chapter_id"] for s in path["steps"]] == [ch1, ch2, py1]
    assert path["steps"][0]["distance"] == 2 and path["steps"][-1]["target"]
    assert path["skills"] == ["Charger des données SQL dans pandas"]


def test_moving_a_course_prunes_invalid_dependencies(data_dir):
    sql_id, (ch1, ch2) = add_course("Bases de données", SQL_CHAPTERS)
    py_id, (py1,) = add_course("Python pour la data", PYTHON_DATA_CHAPTERS)
    call(server.add_dependency, chapter_id=py1, prerequisite_chapter_id=ch2)
    call(server.add_dependency, chapter_id=ch2, prerequisite_chapter_id=ch1)

    result = call(server.move_course, course_id=py_id, position=1)
    assert [c["id"] for c in result["courses"]] == [py_id, sql_id]
    assert result["dependencies_removed"] == 1  # Python ne peut plus dépendre de SQL, placé après lui


def test_subgraph_of_a_course_includes_cross_course_links(data_dir):
    sql_id, (ch1, ch2) = add_course("Bases de données", SQL_CHAPTERS)
    py_id, (py1,) = add_course("Python pour la data", PYTHON_DATA_CHAPTERS)
    call(server.add_dependency, chapter_id=py1, prerequisite_chapter_id=ch2)

    graph = call(server.get_knowledge_graph, course_id=py_id)
    uids = {n["uid"] for n in graph["nodes"]}
    assert {f"chapter:{py1}", f"chapter:{ch2}", f"course:{sql_id}", f"course:{py_id}"} <= uids
    assert f"chapter:{ch1}" not in uids
    assert any(e["type"] == "DEPENDS_ON" for e in graph["edges"])

    only_chapters = call(server.get_knowledge_graph, node_types=["Chapter"])
    assert {n["type"] for n in only_chapters["nodes"]} == {"Chapter"}


def test_delete_course_cleans_graph_and_orphans(data_dir):
    sql_id, _ = add_course("Bases de données", SQL_CHAPTERS)
    call(server.delete_course, course_id=sql_id)
    stats = call(server.graph_stats)
    assert sum(stats["nodes"].values()) == 0 and sum(stats["edges"].values()) == 0
    assert call(server.get_course, course_id=sql_id)["code"] == 404


def test_find_concept(data_dir):
    _, (ch1, ch2) = add_course("Bases de données", SQL_CHAPTERS)
    result = call(server.find_concept, name="clé primaire")
    assert [c["chapter_id"] for c in result["taught_in"]] == [ch1]
    assert [c["chapter_id"] for c in result["required_by"]] == [ch2]
