"""Index vectoriel des comptes-rendus (partie « Retrieval » du RAG).

Chaque morceau de compte-rendu est transformé en vecteur (embedding all-MiniLM-L6-v2,
calculé en local par ChromaDB) et rangé avec le titre, la date et la position
(page / minute) de la réunion. La recherche renvoie les morceaux les plus proches
d'une question, avec un score de similarité.

Un seul processus doit ouvrir l'index ChromaDB : c'est pourquoi il vit dans le serveur MCP.
"""
from functools import lru_cache

from . import config


@lru_cache(maxsize=4)
def _collection(path):
    import chromadb  # import tardif : chromadb est lourd à charger

    client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(config.COLLECTION_NAME, metadata={"hnsw:space": "cosine"})


def collection():
    return _collection(str(config.CHROMA_DIR))


def warmup():
    """Charge ChromaDB et le modèle d'embedding AVANT de servir les requêtes.

    Sous Windows, en transport stdio, un thread est bloqué en lecture sur stdin ; le premier
    chargement de ChromaDB/ONNX (qui interroge la plateforme) se bloque alors indéfiniment.
    Le faire au démarrage évite ce blocage et rend aussi la première recherche plus rapide.
    """
    import platform

    platform.uname()
    col = collection()
    embed = getattr(col, "_embedding_function", None)
    if embed is not None:
        embed(["warmup"])


def index_meeting(meeting_id, title, meeting_date, chunks):
    chunks = [c for c in chunks if (c.get("text") or "").strip()]
    if not chunks:
        return 0
    remove_meeting(meeting_id)  # ré-indexation propre si la réunion est retraitée
    collection().add(
        ids=[f"{meeting_id}-{i}" for i in range(len(chunks))],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[
            {"meeting_id": meeting_id, "title": title, "date": meeting_date, "label": chunk.get("label", "texte")}
            for chunk in chunks
        ],
    )
    return len(chunks)


def remove_meeting(meeting_id):
    collection().delete(where={"meeting_id": meeting_id})


def search(query, k=None, meeting_id=None):
    col = collection()
    count = col.count()
    if count == 0 or not query.strip():
        return []
    options = {"where": {"meeting_id": meeting_id}} if meeting_id else {}
    results = col.query(query_texts=[query], n_results=min(k or config.TOP_K, count), **options)
    passages = []
    rows = zip(results["documents"][0], results["metadatas"][0], results["distances"][0], strict=False)
    for text, meta, distance in rows:
        passages.append({"text": text, **meta, "score": round(1 - float(distance), 3)})
    return passages
