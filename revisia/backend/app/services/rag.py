"""RAG : on retrouve les passages du cours utiles, puis le LLM répond en les citant.

1. Indexation : chaque morceau du cours est transformé en vecteur (embedding)
   et rangé dans ChromaDB.
2. Recherche : la question est aussi transformée en vecteur, et ChromaDB renvoie
   les morceaux les plus proches.
3. Génération : le LLM reçoit la question + ces morceaux numérotés et doit citer
   ses sources [1], [2]...
"""
import chromadb

from ..config import CHROMA_DIR, TOP_K
from .llm import LANGUAGE_NAMES, ask_llm

_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
# ChromaDB utilise par défaut un petit modèle d'embedding (all-MiniLM-L6-v2) qui tourne en local
_collection = _client.get_or_create_collection("courses")


def index_course(course_id, title, chunks):
    if not chunks:
        return
    _collection.add(
        ids=[f"{course_id}-{i}" for i in range(len(chunks))],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[{"course_id": course_id, "title": title, "label": chunk["label"]} for chunk in chunks],
    )


def remove_course(course_id):
    _collection.delete(where={"course_id": course_id})


def search(question, course_id=None, k=TOP_K):
    if _collection.count() == 0:
        return []
    where = {"course_id": course_id} if course_id else None
    results = _collection.query(query_texts=[question], n_results=k, where=where)
    passages = []
    for text, meta in zip(results["documents"][0], results["metadatas"][0]):
        passages.append({"text": text, "title": meta["title"], "label": meta["label"], "course_id": meta["course_id"]})
    return passages


def answer_question(question, course_id=None, language="fr"):
    passages = search(question, course_id)
    if not passages:
        return {"answer": "Aucun cours n'est encore importé. Ajoute un cours d'abord.", "sources": []}

    context = "\n\n".join(
        f"[{i}] ({p['title']}, {p['label']})\n{p['text']}" for i, p in enumerate(passages, start=1)
    )
    lang = LANGUAGE_NAMES.get(language, "français")
    system = (
        f"Tu es un assistant de révision. Réponds en {lang} uniquement à partir des extraits fournis. "
        "Cite les extraits utilisés avec leur numéro entre crochets, par exemple [1]. "
        "Si la réponse n'est pas dans les extraits, dis-le honnêtement."
    )
    user = f"EXTRAITS :\n{context}\n\nQUESTION : {question}"
    answer = ask_llm([{"role": "system", "content": system}, {"role": "user", "content": user}])

    sources = [
        {"number": i, "title": p["title"], "label": p["label"], "course_id": p["course_id"], "excerpt": p["text"][:300]}
        for i, p in enumerate(passages, start=1)
    ]
    return {"answer": answer, "sources": sources}
