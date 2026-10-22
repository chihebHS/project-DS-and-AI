"""API FastAPI de l'assistant de révision."""
import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import database as db
from .config import AUDIO_EXTENSIONS, GROQ_API_KEY, PDF_EXTENSIONS, TEXT_EXTENSIONS, UPLOAD_DIR
from .services import documents, llm, rag, transcription

app = FastAPI(title="RevisIA - Assistant de révision")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

db.init_db()


class ChatRequest(BaseModel):
    question: str
    course_id: int | None = None
    language: str = "fr"


@app.get("/api/health")
def health():
    return {"status": "ok", "groq_key_configured": bool(GROQ_API_KEY)}


@app.get("/api/courses")
def get_courses():
    return db.list_courses()


@app.get("/api/courses/{course_id}")
def get_course(course_id: int):
    course = db.get_course(course_id)
    if not course:
        raise HTTPException(404, "Cours introuvable")
    return course


@app.post("/api/courses")
def upload_course(title: str = Form(...), language: str = Form("fr"), file: UploadFile = File(...)):
    extension = Path(file.filename).suffix.lower()
    if extension in AUDIO_EXTENSIONS:
        source_type = "audio"
    elif extension in PDF_EXTENSIONS:
        source_type = "pdf"
    elif extension in TEXT_EXTENSIONS:
        source_type = "texte"
    else:
        raise HTTPException(400, f"Format non supporté : {extension}")

    course_id = db.create_course(title, language, source_type, file.filename)
    saved_path = UPLOAD_DIR / f"{course_id}{extension}"
    with open(saved_path, "wb") as out:
        shutil.copyfileobj(file.file, out)

    try:
        # 1. Extraire le texte du fichier
        if source_type == "audio":
            sections = transcription.transcribe_audio(saved_path, language)
        elif source_type == "pdf":
            sections = documents.read_pdf(saved_path)
        else:
            sections = documents.read_text_file(saved_path)

        full_text = "\n\n".join(section["text"] for section in sections)
        if not full_text.strip():
            raise ValueError("Aucun texte n'a pu être extrait du fichier.")
        db.update_course(course_id, content=full_text)

        # 2. Indexer les morceaux pour la recherche (RAG)
        rag.index_course(course_id, title, documents.split_into_chunks(sections))

        # 3. Générer le résumé, les notions clés et le quiz
        material = llm.generate_study_material(full_text, language)
        db.update_course(course_id, **material, status="ready")
    except Exception as error:
        db.update_course(course_id, status="error", error=str(error))

    return db.get_course(course_id)


@app.delete("/api/courses/{course_id}")
def remove_course(course_id: int):
    rag.remove_course(course_id)
    db.delete_course(course_id)
    for path in UPLOAD_DIR.glob(f"{course_id}.*"):
        path.unlink()
    return {"deleted": course_id}


@app.post("/api/chat")
def chat(request: ChatRequest):
    if not request.question.strip():
        raise HTTPException(400, "La question est vide")
    try:
        return rag.answer_question(request.question, request.course_id, request.language)
    except Exception as error:
        raise HTTPException(500, str(error))
