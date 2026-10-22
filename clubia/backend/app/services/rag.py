"""RAG sur l'historique des réunions du club.

1. Indexation : chaque morceau de compte-rendu est transformé en vecteur (embedding)
   et rangé dans ChromaDB avec le titre et la date de la réunion.
2. Recherche : la question est transformée en vecteur, et ChromaDB renvoie
   les morceaux les plus proches.
3. Génération : le LLM reçoit la question, ces morceaux numérotés et la liste
   actuelle des tâches. Il répond en citant ses sources [1], [2]...
"""
import chromadb

from .. import database as db
from ..config import CHROMA_DIR, TOP_K
from .llm import LANGUAGE_NAMES, ask_llm

STATUS_LABELS = {"a_faire": "à faire", "en_cours": "en cours", "termine": "terminé"}

_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
# ChromaDB utilise par défaut un petit modèle d'embedding (all-MiniLM-L6-v2) qui tourne en local
_collection = _client.get_or_create_collection("meetings")


def index_meeting(meeting_id, title, meeting_date, chunks):
    if not chunks:
        return
    _collection.add(
        ids=[f"{meeting_id}-{i}" for i in range(len(chunks))],
        documents=[chunk["text"] for chunk in chunks],
        metadatas=[
            {"meeting_id": meeting_id, "title": title, "date": meeting_date, "label": chunk["label"]}
            for chunk in chunks
        ],
    )


def remove_meeting(meeting_id):
    _collection.delete(where={"meeting_id": meeting_id})


def search(question, k=TOP_K):
    if _collection.count() == 0:
        return []
    results = _collection.query(query_texts=[question], n_results=min(k, _collection.count()))
    return [
        {"text": text, **meta}
        for text, meta in zip(results["documents"][0], results["metadatas"][0])
    ]


def tasks_as_text():
    """La liste des tâches à jour, pour que l'assistant connaisse leur avancement."""
    lines = []
    for t in db.list_tasks()[:60]:
        due = t["due_date"] or "sans date"
        late = " (EN RETARD)" if t["overdue"] else ""
        lines.append(f"- {t['description']} | {t['assignee']} | échéance : {due} | {STATUS_LABELS[t['status']]}{late}")
    return "\n".join(lines) or "Aucune tâche."


def answer_question(question, language="fr"):
    passages = search(question)
    if not passages:
        return {"answer": "Aucune réunion n'est encore importée. Ajoute un compte-rendu d'abord.", "sources": []}

    context = "\n\n".join(
        f"[{i}] (Réunion « {p['title']} » du {p['date']}, {p['label']})\n{p['text']}"
        for i, p in enumerate(passages, start=1)
    )
    lang = LANGUAGE_NAMES.get(language, "français")
    system = (
        f"Tu es l'assistant d'un club étudiant. Réponds en {lang}, de façon courte et claire, "
        "uniquement à partir des extraits de comptes-rendus et de la liste des tâches fournis. "
        "Quand tu utilises un extrait, cite son numéro entre crochets, par exemple [1]. "
        "Pour l'avancement des tâches, base-toi sur la LISTE DES TÂCHES, qui est à jour. "
        "Si l'information n'est pas disponible, dis-le honnêtement."
    )
    user = f"EXTRAITS DES RÉUNIONS :\n{context}\n\nLISTE DES TÂCHES :\n{tasks_as_text()}\n\nQUESTION : {question}"
    answer = ask_llm([{"role": "system", "content": system}, {"role": "user", "content": user}])

    sources = [
        {"number": i, "title": p["title"], "date": p["date"], "label": p["label"],
         "meeting_id": p["meeting_id"], "excerpt": p["text"][:300]}
        for i, p in enumerate(passages, start=1)
    ]
    return {"answer": answer, "sources": sources}
