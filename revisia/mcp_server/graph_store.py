"""Graphe de connaissances des cours (modèle « property graph », comme Neo4j).

Nœuds (label → identifiant) :
    (:Course  {uid: "course:3"})     un cours importé
    (:Chapter {uid: "chapter:12"})   une partie d'un cours
    (:Concept {uid: "concept:jointure"})  une notion (partagée entre les cours)
    (:Skill   {uid: "skill:ecrire-une-requete-sql"})  une compétence à acquérir

Relations :
    (Course)-[:HAS_CHAPTER]->(Chapter)
    (Chapter)-[:NEXT]->(Chapter)            ordre des chapitres dans un cours
    (Chapter)-[:COVERS]->(Concept)          notion enseignée dans le chapitre
    (Chapter)-[:TEACHES]->(Skill)           compétence à acquérir
    (Chapter)-[:REQUIRES]->(Concept)        prérequis (notion à connaître avant)
    (Chapter)-[:DEPENDS_ON {reason, concepts}]->(Chapter)
        le chapitre dépend d'un chapitre PRÉCÉDENT (même cours ou cours antérieur)

Deux implémentations, même interface :
- SqliteGraphStore : tables `graph_nodes` / `graph_edges` (développement, tests, sans service externe) ;
- Neo4jGraphStore  : vraie base Neo4j en Cypher (Docker Compose, Kubernetes).
"""
import json
import re
import unicodedata
from collections import deque

from . import config

NODE_TYPES = ("Course", "Chapter", "Concept", "Skill")
EDGE_TYPES = ("HAS_CHAPTER", "NEXT", "COVERS", "TEACHES", "REQUIRES", "DEPENDS_ON")


def slug(text):
    """« Clé étrangère » → « cle-etrangere » : deux cours qui citent la même notion partagent le nœud."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"\([^)]*\)", " ", text)  # « SQL (Structured Query Language) » → « sql »
    text = re.sub(r"\b(les?|la|l|des?|du|d|un|une|the|a|an|of)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def course_uid(course_id):
    return f"course:{course_id}"


def chapter_uid(chapter_id):
    return f"chapter:{chapter_id}"


def chapter_id_of(uid):
    return int(uid.split(":", 1)[1])


class GraphStore:
    """Opérations de haut niveau, communes aux deux implémentations."""

    backend = "abstract"

    # --- primitives à implémenter ---
    def init(self): ...
    def upsert_node(self, uid, node_type, label, props, keep_existing=False): ...
    def delete_nodes(self, uids): ...
    def add_edge(self, source, target, edge_type, props=None): ...
    def delete_edge(self, source, target, edge_type): ...
    def nodes(self): ...
    def edges(self): ...
    def close(self): ...

    # --- opérations métier ---
    def save_course_graph(self, course, chapters):
        """(Re)construit le sous-graphe d'un cours.

        chapters : [{"id", "position", "title", "summary", "concepts": [{"name", "definition"}],
                     "skills": [str], "prerequisites": [str]}]
        """
        self.delete_course_graph(course["id"])
        cuid = course_uid(course["id"])
        self.upsert_node(cuid, "Course", course["title"], {"course_id": course["id"], "position": course["position"]})
        previous = None
        for chapter in chapters:
            uid = chapter_uid(chapter["id"])
            self.upsert_node(uid, "Chapter", chapter["title"], {
                "chapter_id": chapter["id"], "course_id": course["id"], "position": chapter["position"],
                "summary": (chapter.get("summary") or "")[:1000]})
            self.add_edge(cuid, uid, "HAS_CHAPTER")
            if previous:
                self.add_edge(previous, uid, "NEXT")
            previous = uid
            for concept in chapter.get("concepts", []):
                key = slug(concept["name"])
                if key:
                    self.upsert_node(f"concept:{key}", "Concept", concept["name"].strip(),
                                     {"definition": (concept.get("definition") or "")[:500]})
                    self.add_edge(uid, f"concept:{key}", "COVERS")
            for skill in chapter.get("skills", []):
                key = slug(skill)
                if key:
                    self.upsert_node(f"skill:{key}", "Skill", skill.strip(), {})
                    self.add_edge(uid, f"skill:{key}", "TEACHES")
            for prerequisite in chapter.get("prerequisites", []):
                key = slug(prerequisite)
                if key:
                    self.upsert_node(f"concept:{key}", "Concept", prerequisite.strip(), {}, keep_existing=True)
                    self.add_edge(uid, f"concept:{key}", "REQUIRES")

    def delete_course_graph(self, course_id):
        doomed = [n["uid"] for n in self.nodes()
                  if n["type"] in ("Course", "Chapter") and n["props"].get("course_id") == course_id]
        self.delete_nodes(doomed)
        self.delete_orphans()

    def delete_orphans(self):
        """Supprime les notions et compétences qui ne sont plus reliées à aucun chapitre."""
        linked = {e["target"] for e in self.edges()}
        self.delete_nodes([n["uid"] for n in self.nodes() if n["type"] in ("Concept", "Skill") and n["uid"] not in linked])

    def chapter_knowledge(self, chapter_id):
        uid = chapter_uid(chapter_id)
        nodes = {n["uid"]: n for n in self.nodes()}
        result = {"covers": [], "teaches": [], "requires": [], "depends_on": [], "required_by": []}
        for e in self.edges():
            if e["source"] == uid and e["type"] in ("COVERS", "TEACHES", "REQUIRES"):
                node = nodes.get(e["target"], {})
                key = {"COVERS": "covers", "TEACHES": "teaches", "REQUIRES": "requires"}[e["type"]]
                result[key].append({"key": e["target"].split(":", 1)[1], "name": node.get("label"),
                                    "definition": node.get("props", {}).get("definition", "")})
            elif e["type"] == "DEPENDS_ON" and uid in (e["source"], e["target"]):
                other = e["target"] if e["source"] == uid else e["source"]
                key = "depends_on" if e["source"] == uid else "required_by"
                result[key].append({"chapter_id": chapter_id_of(other), "title": nodes.get(other, {}).get("label"),
                                    **e["props"]})
        return result

    def chapters_covering(self, concept_keys):
        wanted = {f"concept:{k}" for k in concept_keys}
        return [{"chapter_id": chapter_id_of(e["source"]), "concept_key": e["target"].split(":", 1)[1]}
                for e in self.edges() if e["type"] == "COVERS" and e["target"] in wanted]

    def add_dependency(self, from_chapter, to_chapter, reason="", concepts=None):
        self.delete_edge(chapter_uid(from_chapter), chapter_uid(to_chapter), "DEPENDS_ON")
        self.add_edge(chapter_uid(from_chapter), chapter_uid(to_chapter), "DEPENDS_ON",
                      {"reason": reason or "", "concepts": list(concepts or [])})

    def remove_dependency(self, from_chapter, to_chapter):
        self.delete_edge(chapter_uid(from_chapter), chapter_uid(to_chapter), "DEPENDS_ON")

    def dependencies(self):
        return [{"from": chapter_id_of(e["source"]), "to": chapter_id_of(e["target"]), **e["props"]}
                for e in self.edges() if e["type"] == "DEPENDS_ON"]

    def ancestors(self, chapter_id):
        """Tous les chapitres dont dépend (directement ou non) ce chapitre, avec leur distance."""
        out = {}
        for dep in self.dependencies():
            out.setdefault(dep["from"], []).append(dep["to"])
        depth, queue = {}, deque([(chapter_id, 0)])
        while queue:
            current, d = queue.popleft()
            for parent in out.get(current, []):
                if parent not in depth:
                    depth[parent] = d + 1
                    queue.append((parent, d + 1))
        return depth

    def subgraph(self, course_id=None, types=None):
        """Nœuds et relations à afficher. Avec course_id : le cours, ses chapitres, leurs notions et
        compétences, plus les chapitres d'AUTRES cours reliés par DEPENDS_ON (relations entre cours)."""
        nodes = {n["uid"]: n for n in self.nodes()}
        edges = self.edges()
        if course_id:
            keep = {uid for uid, n in nodes.items()
                    if n["type"] in ("Course", "Chapter") and n["props"].get("course_id") == course_id}
            for e in edges:
                if e["source"] in keep and e["type"] in ("COVERS", "TEACHES", "REQUIRES"):
                    keep.add(e["target"])
            for e in edges:
                if e["type"] == "DEPENDS_ON" and (e["source"] in keep or e["target"] in keep):
                    keep.update((e["source"], e["target"]))
            for uid in list(keep):  # cours des chapitres externes reliés
                if nodes.get(uid, {}).get("type") == "Chapter":
                    keep.add(course_uid(nodes[uid]["props"]["course_id"]))
            nodes = {uid: n for uid, n in nodes.items() if uid in keep}
        if types:
            nodes = {uid: n for uid, n in nodes.items() if n["type"] in types}
        edges = [e for e in edges if e["source"] in nodes and e["target"] in nodes]
        return {"nodes": list(nodes.values()), "edges": edges, "backend": self.backend}

    def stats(self):
        nodes, edges = self.nodes(), self.edges()
        return {"backend": self.backend,
                "nodes": {t: sum(n["type"] == t for n in nodes) for t in NODE_TYPES},
                "edges": {t: sum(e["type"] == t for e in edges) for t in EDGE_TYPES}}


class SqliteGraphStore(GraphStore):
    backend = "sqlite"

    def __init__(self, connect):
        self._connect = connect

    def init(self):
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS graph_nodes (
                    uid TEXT PRIMARY KEY, type TEXT NOT NULL, label TEXT NOT NULL, props TEXT DEFAULT '{}');
                CREATE TABLE IF NOT EXISTS graph_edges (
                    source TEXT NOT NULL REFERENCES graph_nodes(uid) ON DELETE CASCADE,
                    target TEXT NOT NULL REFERENCES graph_nodes(uid) ON DELETE CASCADE,
                    type TEXT NOT NULL, props TEXT DEFAULT '{}',
                    PRIMARY KEY (source, target, type));
                CREATE INDEX IF NOT EXISTS idx_edges_target ON graph_edges(target);
                """
            )

    def upsert_node(self, uid, node_type, label, props, keep_existing=False):
        with self._connect() as conn:
            if keep_existing:
                conn.execute("INSERT OR IGNORE INTO graph_nodes (uid, type, label, props) VALUES (?, ?, ?, ?)",
                             (uid, node_type, label, json.dumps(props, ensure_ascii=False)))
                return
            row = conn.execute("SELECT props FROM graph_nodes WHERE uid = ?", (uid,)).fetchone()
            merged = {**(json.loads(row[0]) if row else {}), **{k: v for k, v in props.items() if v not in ("", None)}}
            conn.execute(
                "INSERT INTO graph_nodes (uid, type, label, props) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(uid) DO UPDATE SET label = excluded.label, props = excluded.props",
                (uid, node_type, label, json.dumps(merged, ensure_ascii=False)))

    def delete_nodes(self, uids):
        if not uids:
            return
        with self._connect() as conn:
            conn.executemany("DELETE FROM graph_nodes WHERE uid = ?", [(u,) for u in uids])

    def add_edge(self, source, target, edge_type, props=None):
        with self._connect() as conn:
            conn.execute("INSERT OR REPLACE INTO graph_edges (source, target, type, props) VALUES (?, ?, ?, ?)",
                         (source, target, edge_type, json.dumps(props or {}, ensure_ascii=False)))

    def delete_edge(self, source, target, edge_type):
        with self._connect() as conn:
            conn.execute("DELETE FROM graph_edges WHERE source = ? AND target = ? AND type = ?",
                         (source, target, edge_type))

    def nodes(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT uid, type, label, props FROM graph_nodes").fetchall()
        return [{"uid": r[0], "type": r[1], "label": r[2], "props": json.loads(r[3] or "{}")} for r in rows]

    def edges(self):
        with self._connect() as conn:
            rows = conn.execute("SELECT source, target, type, props FROM graph_edges").fetchall()
        return [{"source": r[0], "target": r[1], "type": r[2], "props": json.loads(r[3] or "{}")} for r in rows]

    def close(self):
        pass


class Neo4jGraphStore(GraphStore):
    """Même graphe, stocké dans Neo4j et interrogé en Cypher."""

    backend = "neo4j"

    def __init__(self, uri, user, password, database="neo4j"):
        from neo4j import GraphDatabase

        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def _run(self, query, **params):
        records, _, _ = self._driver.execute_query(query, params, database_=self._database)
        return records

    def init(self):
        self._driver.verify_connectivity()
        for label in NODE_TYPES:
            self._run(f"CREATE CONSTRAINT {label.lower()}_uid IF NOT EXISTS FOR (n:{label}) REQUIRE n.uid IS UNIQUE")

    def upsert_node(self, uid, node_type, label, props, keep_existing=False):
        if node_type not in NODE_TYPES:
            raise ValueError(f"Type de nœud inconnu : {node_type}")
        props = {k: v for k, v in props.items() if v not in ("", None)}
        if keep_existing:
            self._run(f"MERGE (n:{node_type} {{uid: $uid}}) ON CREATE SET n.label = $label, n += $props",
                      uid=uid, label=label, props=props)
        else:
            self._run(f"MERGE (n:{node_type} {{uid: $uid}}) SET n.label = $label, n += $props",
                      uid=uid, label=label, props=props)

    def delete_nodes(self, uids):
        if uids:
            self._run("MATCH (n) WHERE n.uid IN $uids DETACH DELETE n", uids=list(uids))

    def add_edge(self, source, target, edge_type, props=None):
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"Type de relation inconnu : {edge_type}")
        self._run(f"MATCH (a {{uid: $source}}), (b {{uid: $target}}) MERGE (a)-[r:{edge_type}]->(b) SET r = $props",
                  source=source, target=target, props=props or {})

    def delete_edge(self, source, target, edge_type):
        self._run(f"MATCH (a {{uid: $source}})-[r:{edge_type}]->(b {{uid: $target}}) DELETE r",
                  source=source, target=target)

    def nodes(self):
        records = self._run("MATCH (n) WHERE n.uid IS NOT NULL RETURN n.uid AS uid, labels(n)[0] AS type,"
                            " n.label AS label, properties(n) AS props")
        return [{"uid": r["uid"], "type": r["type"], "label": r["label"],
                 "props": {k: v for k, v in r["props"].items() if k not in ("uid", "label")}} for r in records]

    def edges(self):
        records = self._run("MATCH (a)-[r]->(b) WHERE a.uid IS NOT NULL AND b.uid IS NOT NULL"
                            " RETURN a.uid AS source, b.uid AS target, type(r) AS type, properties(r) AS props")
        return [{"source": r["source"], "target": r["target"], "type": r["type"], "props": dict(r["props"])}
                for r in records]

    def ancestors(self, chapter_id):
        """Parcours en Cypher : chemins de longueur variable sur DEPENDS_ON."""
        records = self._run(
            "MATCH p = (c:Chapter {uid: $uid})-[:DEPENDS_ON*1..20]->(a:Chapter)"
            " RETURN a.uid AS uid, min(length(p)) AS depth", uid=chapter_uid(chapter_id))
        return {chapter_id_of(r["uid"]): r["depth"] for r in records}

    def close(self):
        self._driver.close()


_store = None


def get_store(connect=None):
    """Neo4j si NEO4J_URI est configuré, sinon SQLite (même fichier que les cours)."""
    global _store
    if _store is None:
        if config.NEO4J_URI:
            store = Neo4jGraphStore(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD, config.NEO4J_DATABASE)
        else:
            from .database import get_connection

            store = SqliteGraphStore(connect or get_connection)
        store.init()  # n'est mémorisé qu'une fois la connexion réussie
        _store = store
    return _store


def reset_store():
    global _store
    if _store is not None:
        _store.close()
    _store = None
