"""API FastAPI de RevisIA.

Le backend ne touche jamais directement aux données : il passe par le serveur MCP.
Il orchestre trois graphes LangGraph :
- l'ingestion d'un cours (chapitres, notions, compétences, prérequis, quiz), en tâche de fond ;
- l'agent linker, qui relie chaque chapitre aux chapitres PRÉCÉDENTS dont il dépend ;
- le chat multi-agents (superviseur + tuteur RAG + navigateur du graphe + examinateur).
"""
import logging
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents.chat import NAVIGATOR_TOOLS, ask, build_chat_graph
from .agents.ingestion import process_course
from .agents.linker import link_course
from .config import (
    AUDIO_EXTENSIONS,
    CHECKPOINT_DB,
    CORS_ORIGINS,
    GROQ_API_KEY,
    LOG_LEVEL,
    MAX_UPLOAD_MB,
    PDF_EXTENSIONS,
    TEXT_EXTENSIONS,
    UPLOAD_TMP_DIR,
)
from .mcp_client import MCPToolError, mcp
from .schemas import ChatRequest, DependencyCreate, PositionUpdate
from .services.llm import LLMNotConfigured

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("revisia")


async def open_checkpointer(stack):
    """Mémoire des conversations : SQLite si possible, sinon en mémoire."""
    if CHECKPOINT_DB:
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            return await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(CHECKPOINT_DB))
        except Exception as error:  # noqa: BLE001
            log.warning("Checkpointer SQLite indisponible (%s) : mémoire volatile", error)
    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        await mcp.start()
        stack.push_async_callback(mcp.stop)
        checkpointer = await open_checkpointer(stack)
        tools = await mcp.langchain_tools(NAVIGATOR_TOOLS)
        app.state.chat_graph = build_chat_graph(mcp, tools, checkpointer)
        log.info("RevisIA prêt : %d outils MCP pour le navigateur", len(tools))
        yield


app = FastAPI(title="RevisIA - Assistant de révision", version="2.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(MCPToolError)
async def mcp_error_handler(_: Request, error: MCPToolError):
    return JSONResponse(status_code=error.code if error.code in (400, 404) else 502, content={"detail": str(error)})


@app.exception_handler(LLMNotConfigured)
async def llm_error_handler(_: Request, error: LLMNotConfigured):
    return JSONResponse(status_code=503, content={"detail": str(error)})


# ---------- Santé (sondes Kubernetes) ----------

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": app.version, "groq_key_configured": bool(GROQ_API_KEY),
            "mcp": {"connected": mcp.connected, "transport": mcp.transport}}


@app.get("/api/ready")
async def ready():
    if not await mcp.ping():
        raise HTTPException(503, "Serveur MCP injoignable")
    return {"status": "ready"}


@app.get("/api/mcp/tools")
async def mcp_tools():
    return [{"name": t.name, "description": (t.description or "").split("\n")[0], "agent": t.name in NAVIGATOR_TOOLS}
            for t in await mcp.list_tools()]


# ---------- Cours ----------

@app.get("/api/courses")
async def get_courses():
    return await mcp.call("list_courses")


@app.get("/api/courses/{course_id}")
async def get_course(course_id: int):
    return await mcp.call("get_course", {"course_id": course_id, "include_content": True})


def detect_source(filename):
    extension = Path(filename).suffix.lower()
    for kind, extensions in (("audio", AUDIO_EXTENSIONS), ("pdf", PDF_EXTENSIONS), ("texte", TEXT_EXTENSIONS)):
        if extension in extensions:
            return kind, extension
    raise HTTPException(400, f"Format non supporté : {extension}")


@app.post("/api/courses", status_code=202)
async def upload_course(
    background: BackgroundTasks,
    title: str = Form(...),
    language: str = Form("fr"),
    text: str = Form(None),
    file: UploadFile | None = File(None),
):
    """Crée le cours et lance l'analyse en tâche de fond (statut processing → ready / error)."""
    if not title.strip():
        raise HTTPException(400, "Le titre est vide")
    if language not in ("fr", "en"):
        raise HTTPException(400, "Langue non supportée")
    file_path, filename = None, None
    if file is not None and file.filename:
        source_type, extension = detect_source(file.filename)
        content = await file.read()
        if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"Fichier trop volumineux (max {MAX_UPLOAD_MB} Mo)")
        file_path = UPLOAD_TMP_DIR / f"{uuid.uuid4().hex}{extension}"
        file_path.write_bytes(content)
        filename = Path(file.filename).name
    elif text and text.strip():
        source_type = "saisie"
    else:
        raise HTTPException(400, "Importe un fichier ou colle le texte du cours.")

    created = await mcp.call("create_course", {"title": title.strip(), "language": language,
                                               "source_type": source_type, "filename": filename or ""})
    background.add_task(process_course, mcp, created["id"], title.strip(), language, source_type,
                        text=text, file_path=str(file_path) if file_path else None)
    return await mcp.call("get_course", {"course_id": created["id"]})


@app.delete("/api/courses/{course_id}")
async def remove_course(course_id: int):
    return await mcp.call("delete_course", {"course_id": course_id})


@app.patch("/api/courses/{course_id}/position")
async def move_course(course_id: int, body: PositionUpdate):
    """Change l'ordre du cursus ; les dépendances devenues invalides sont supprimées."""
    return await mcp.call("move_course", {"course_id": course_id, "position": body.position})


@app.post("/api/courses/{course_id}/relink")
async def relink_course(course_id: int):
    """Relance l'agent linker (utile après avoir importé ou réordonné des cours)."""
    course = await mcp.call("get_course", {"course_id": course_id})
    return await link_course(mcp, course_id, course["language"])


# ---------- Chapitres, graphe et parcours ----------

@app.get("/api/chapters/{chapter_id}")
async def get_chapter(chapter_id: int):
    return await mcp.call("get_chapter", {"chapter_id": chapter_id})


@app.get("/api/chapters/{chapter_id}/path")
async def chapter_path(chapter_id: int):
    return await mcp.call("learning_path", {"chapter_id": chapter_id})


@app.get("/api/chapters/{chapter_id}/candidates")
async def chapter_candidates(chapter_id: int):
    return await mcp.call("find_prerequisite_candidates", {"chapter_id": chapter_id})


@app.post("/api/dependencies", status_code=201)
async def add_dependency(body: DependencyCreate):
    return await mcp.call("add_dependency", body.model_dump())


@app.delete("/api/dependencies")
async def remove_dependency(chapter_id: int, prerequisite_chapter_id: int):
    return await mcp.call("remove_dependency", {"chapter_id": chapter_id,
                                                "prerequisite_chapter_id": prerequisite_chapter_id})


@app.get("/api/graph")
async def knowledge_graph(course_id: int | None = None, types: list[str] = Query(default=[])):
    return await mcp.call("get_knowledge_graph", {"course_id": course_id or 0, "node_types": types or None})


@app.get("/api/graph/stats")
async def graph_stats():
    return await mcp.call("graph_stats")


@app.get("/api/concepts")
async def find_concept(name: str):
    return await mcp.call("find_concept", {"name": name})


# ---------- Chat multi-agents ----------

@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request):
    if not request.question.strip():
        raise HTTPException(400, "La question est vide")
    thread_id = request.thread_id or uuid.uuid4().hex
    try:
        return await ask(http_request.app.state.chat_graph, request.question.strip(), request.language, thread_id,
                         request.course_id)
    except (MCPToolError, LLMNotConfigured):
        raise
    except Exception as error:
        log.exception("Erreur du graphe de chat")
        raise HTTPException(500, f"Erreur de l'assistant : {error}") from error
