"""Index vectoriel ChromaDB (embeddings locaux all-MiniLM-L6-v2).

Deux collections :
- `courses`  : les morceaux du texte des cours (partie « Retrieval » du RAG, avec page / minute) ;
- `concepts` : les notions enseignées par chaque chapitre (« nom : définition »). Elles servent à
  retrouver quel chapitre PRÉCÉDENT enseigne un prérequis, même s'il est formulé autrement.

Un seul processus doit ouvrir l'index ChromaDB : c'est pourquoi il vit dans le serveur MCP.
"""
from functools import lru_cache

from . import config


@lru_cache(maxsize=8)
def _collection(path, name):
    import chromadb  # import tardif : chromadb est lourd à charger

    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(name, metadata={"hnsw:space": "cosine"})


def chunks_collection():
    return _collection(str(config.CHROMA_DIR), "courses")


def concepts_collection():
    return _collection(str(config.CHROMA_DIR), "concepts")


def warmup():
    """Charge ChromaDB et le modèle d'embedding AVANT de servir les requêtes.

    Sous Windows, en transport stdio, un thread est bloqué en lecture sur stdin ; le premier
    chargement de ChromaDB/ONNX se bloque alors indéfiniment. Le faire au démarrage l'évite.
    """
    import platform

    platform.uname()
    col = chunks_collection()
    concepts_collection()
    embed = getattr(col, "_embedding_function", None)
    if embed is not None:
        embed(["warmup"])


def _query(col, text, k, where=None):
    count = col.count()
    if count == 0 or not text.strip():
        return []
    options = {"where": where} if where else {}
    results = col.query(query_texts=[text], n_results=min(k, count), **options)
    rows = zip(results["documents"][0], results["metadatas"][0], results["distances"][0], strict=False)
    return [{"text": doc, **meta, "score": round(1 - float(dist), 3)} for doc, meta, dist in rows]


# ---------- Morceaux de cours ----------

def index_course(course_id, title, chunks):
    chunks = [c for c in chunks if (c.get("text") or "").strip()]
    chunks_collection().delete(where={"course_id": course_id})
    if not chunks:
        return 0
    chunks_collection().add(
        ids=[f"{course_id}-{i}" for i in range(len(chunks))],
        documents=[c["text"] for c in chunks],
        metadatas=[{"course_id": course_id, "title": title, "label": c.get("label", "texte")} for c in chunks],
    )
    return len(chunks)


def search(query, k=None, course_id=None):
    return _query(chunks_collection(), query, k or config.TOP_K, {"course_id": course_id} if course_id else None)


# ---------- Notions des chapitres ----------

def index_concepts(course_id, chapters):
    """chapters : [{"id", "concepts": [{"name", "definition"}]}]."""
    remove_concepts(course_id)
    col = concepts_collection()
    ids, docs, metas = [], [], []
    for chapter in chapters:
        for i, concept in enumerate(chapter.get("concepts", [])):
            ids.append(f"{chapter['id']}-{i}")
            docs.append(f"{concept['name']} : {concept.get('definition', '')}".strip(" :"))
            metas.append({"course_id": course_id, "chapter_id": chapter["id"], "name": concept["name"]})
    if ids:
        col.add(ids=ids, documents=docs, metadatas=metas)
    return len(ids)


def search_concepts(text, k=8):
    return _query(concepts_collection(), text, k)


def remove_concepts(course_id):
    concepts_collection().delete(where={"course_id": course_id})


def remove_course(course_id):
    chunks_collection().delete(where={"course_id": course_id})
    remove_concepts(course_id)
