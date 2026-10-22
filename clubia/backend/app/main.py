"""API FastAPI de ClubIA : comptes-rendus, tâches et questions sur l'historique."""
import shutil
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import database as db
from .config import AUDIO_EXTENSIONS, GROQ_API_KEY, PDF_EXTENSIONS, TASK_STATUSES, TEXT_EXTENSIONS, UPLOAD_DIR
from .services import documents, llm, rag, transcription

app = FastAPI(title="ClubIA - Assistant de club étudiant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174", "http://127.0.0.1:5174"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


class TaskCreate(BaseModel):
    description: str
    assignee: str = "Non attribué"
    due_date: str | None = None
    meeting_id: int | None = None


class TaskUpdate(BaseModel):
    description: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    status: str | None = None


class ChatRequest(BaseModel):
    question: str
    language: str = "fr"


@app.get("/api/health")
def health():
    return {"status": "ok", "groq_key_configured": bool(GROQ_API_KEY)}


@app.get("/api/stats")
def stats():
    return db.get_stats()


# ---------- Réunions ----------

@app.get("/api/meetings")
def get_meetings():
    return db.list_meetings()


@app.get("/api/meetings/{meeting_id}")
def get_meeting(meeting_id: int):
    meeting = db.get_meeting(meeting_id)
    if not meeting:
        raise HTTPException(404, "Réunion introuvable")
    return meeting


@app.post("/api/meetings")
def create_meeting(
    title: str = Form(...),
    meeting_date: str = Form(None),
    language: str = Form("fr"),
    text: str = Form(None),
    file: UploadFile | None = File(None),
):
    """Un compte-rendu peut être collé directement (text) ou importé (PDF, TXT, audio)."""
    meeting_date = meeting_date or date.today().isoformat()

    if file is not None and file.filename:
        extension = Path(file.filename).suffix.lower()
        if extension in AUDIO_EXTENSIONS:
            source_type = "audio"
        elif extension in PDF_EXTENSIONS:
            source_type = "pdf"
        elif extension in TEXT_EXTENSIONS:
            source_type = "texte"
        else:
            raise HTTPException(400, f"Format non supporté : {extension}")
    elif text and text.strip():
        source_type = "saisie"
    else:
        raise HTTPException(400, "Colle le compte-rendu ou importe un fichier.")

    meeting_id = db.create_meeting(title, meeting_date, language, source_type)

    try:
        # 1. Récupérer le texte du compte-rendu
        if source_type == "saisie":
            sections = [{"label": "compte-rendu", "text": text.strip()}]
        else:
            saved_path = UPLOAD_DIR / f"{meeting_id}{extension}"
            with open(saved_path, "wb") as out:
                shutil.copyfileobj(file.file, out)
            if source_type == "audio":
                sections = transcription.transcribe_audio(saved_path, language)
            elif source_type == "pdf":
                sections = documents.read_pdf(saved_path)
            else:
                sections = documents.read_text_file(saved_path)

        full_text = "\n\n".join(section["text"] for section in sections)
        if not full_text.strip():
            raise ValueError("Aucun texte n'a pu être extrait.")
        db.update_meeting(meeting_id, content=full_text)

        # 2. Indexer pour pouvoir poser des questions sur l'historique (RAG)
        rag.index_meeting(meeting_id, title, meeting_date, documents.split_into_chunks(sections))

        # 3. Extraire le résumé, les décisions et les tâches avec le LLM
        info = llm.extract_meeting_info(full_text, meeting_date, language)
        for task in info["tasks"]:
            if task.get("description"):
                db.add_task(meeting_id, task["description"], task.get("assignee"), task.get("due_date"))
        db.update_meeting(meeting_id, summary=info["summary"], decisions=info["decisions"], status="ready")
    except Exception as error:
        db.update_meeting(meeting_id, status="error", error=str(error))

    return db.get_meeting(meeting_id)


@app.delete("/api/meetings/{meeting_id}")
def remove_meeting(meeting_id: int):
    rag.remove_meeting(meeting_id)
    db.delete_meeting(meeting_id)
    for path in UPLOAD_DIR.glob(f"{meeting_id}.*"):
        path.unlink()
    return {"deleted": meeting_id}


# ---------- Tâches ----------

@app.get("/api/tasks")
def get_tasks(status: str | None = None, assignee: str | None = None):
    return db.list_tasks(status=status, assignee=assignee)


@app.post("/api/tasks")
def create_task(task: TaskCreate):
    if not task.description.strip():
        raise HTTPException(400, "La description est vide")
    task_id = db.add_task(task.meeting_id, task.description.strip(), task.assignee.strip(), task.due_date)
    return {"id": task_id}


@app.patch("/api/tasks/{task_id}")
def edit_task(task_id: int, changes: TaskUpdate):
    fields = changes.model_dump(exclude_unset=True)
    if "status" in fields and fields["status"] not in TASK_STATUSES:
        raise HTTPException(400, "Statut invalide")
    if fields:
        db.update_task(task_id, **fields)
    return {"updated": task_id}


@app.delete("/api/tasks/{task_id}")
def remove_task(task_id: int):
    db.delete_task(task_id)
    return {"deleted": task_id}


# ---------- Questions ----------

@app.post("/api/chat")
def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(400, "La question est vide")
    try:
        return rag.answer_question(request.question, request.language)
    except Exception as error:
        raise HTTPException(500, str(error))
