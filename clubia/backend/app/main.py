"""API FastAPI de ClubIA.

Le backend ne touche jamais directement aux données : il passe par le serveur MCP.
Il orchestre deux graphes LangGraph :
- l'ingestion d'un compte-rendu (en tâche de fond, la réunion passe de « processing » à « ready ») ;
- le chat multi-agents (superviseur + archiviste RAG + gestionnaire des tâches + analyste).
"""
import logging
import uuid
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents.chat import TASK_TOOLS, ask, build_chat_graph
from .agents.ingestion import process_meeting
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
from .schemas import ChatRequest, MemberCreate, MemberUpdate, MergeRequest, TaskCreate, TaskUpdate
from .services.llm import LLMNotConfigured

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s [%(name)s] %(message)s")
log = logging.getLogger("clubia")


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
        tools = await mcp.langchain_tools(TASK_TOOLS)
        app.state.chat_graph = build_chat_graph(mcp, tools, checkpointer)
        log.info("ClubIA prêt : %d outils MCP pour l'agent des tâches", len(tools))
        yield


app = FastAPI(title="ClubIA - Assistant de club étudiant", version="2.0.0", lifespan=lifespan)
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
    """Liveness : le processus répond. Donne aussi l'état de la clé Groq et du serveur MCP."""
    return {"status": "ok", "version": app.version, "groq_key_configured": bool(GROQ_API_KEY),
            "mcp": {"connected": mcp.connected, "transport": mcp.transport}}


@app.get("/api/ready")
async def ready():
    """Readiness : le serveur MCP répond au ping."""
    if not await mcp.ping():
        raise HTTPException(503, "Serveur MCP injoignable")
    return {"status": "ready"}


@app.get("/api/mcp/tools")
async def mcp_tools():
    return [{"name": t.name, "description": (t.description or "").split("\n")[0], "agent": t.name in TASK_TOOLS}
            for t in await mcp.list_tools()]


@app.get("/api/stats")
async def stats():
    return await mcp.call("get_stats")


# ---------- Réunions ----------

@app.get("/api/meetings")
async def get_meetings():
    return await mcp.call("list_meetings")


@app.get("/api/meetings/{meeting_id}")
async def get_meeting(meeting_id: int):
    return await mcp.call("get_meeting", {"meeting_id": meeting_id, "include_content": True})


def detect_source(filename):
    extension = Path(filename).suffix.lower()
    for kind, extensions in (("audio", AUDIO_EXTENSIONS), ("pdf", PDF_EXTENSIONS), ("texte", TEXT_EXTENSIONS)):
        if extension in extensions:
            return kind, extension
    raise HTTPException(400, f"Format non supporté : {extension}")


@app.post("/api/meetings", status_code=202)
async def create_meeting(
    background: BackgroundTasks,
    title: str = Form(...),
    meeting_date: str = Form(None),
    language: str = Form("fr"),
    text: str = Form(None),
    file: UploadFile | None = File(None),
):
    """Crée la réunion et lance l'analyse en tâche de fond. Le frontend suit le statut (processing → ready)."""
    if not title.strip():
        raise HTTPException(400, "Le titre est vide")
    if language not in ("fr", "en"):
        raise HTTPException(400, "Langue non supportée")
    try:
        meeting_date = date.fromisoformat(meeting_date).isoformat() if meeting_date else date.today().isoformat()
    except ValueError as error:
        raise HTTPException(400, "Date invalide (format AAAA-MM-JJ)") from error

    file_path = None
    if file is not None and file.filename:
        source_type, extension = detect_source(file.filename)
        content = await file.read()
        if len(content) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"Fichier trop volumineux (max {MAX_UPLOAD_MB} Mo)")
        file_path = UPLOAD_TMP_DIR / f"{uuid.uuid4().hex}{extension}"
        file_path.write_bytes(content)
    elif text and text.strip():
        source_type = "saisie"
    else:
        raise HTTPException(400, "Colle le compte-rendu ou importe un fichier.")

    created = await mcp.call("create_meeting", {"title": title.strip(), "meeting_date": meeting_date,
                                                "language": language, "source_type": source_type})
    background.add_task(process_meeting, mcp, created["id"], title.strip(), meeting_date, language, source_type,
                        text=text, file_path=str(file_path) if file_path else None)
    return await mcp.call("get_meeting", {"meeting_id": created["id"]})


@app.delete("/api/meetings/{meeting_id}")
async def remove_meeting(meeting_id: int):
    return await mcp.call("delete_meeting", {"meeting_id": meeting_id})


# ---------- Tâches ----------

@app.get("/api/tasks")
async def get_tasks(status: str | None = None, assignee: str | None = None, overdue: bool = False):
    return await mcp.call("list_tasks", {"status": status or "", "assignee": assignee or "", "overdue_only": overdue})


@app.post("/api/tasks", status_code=201)
async def create_task(task: TaskCreate):
    return await mcp.call("create_task", {"description": task.description, "assignee": task.assignee,
                                          "due_date": task.due_date or "", "meeting_id": task.meeting_id or 0})


@app.patch("/api/tasks/{task_id}")
async def edit_task(task_id: int, changes: TaskUpdate):
    fields = changes.model_dump(exclude_unset=True)
    if "due_date" in fields and not fields["due_date"]:
        fields["due_date"] = "none"  # retirer l'échéance
    if fields.get("assignee") == "":
        fields["assignee"] = "Non attribué"
    return await mcp.call("update_task", {"task_id": task_id, **{k: v for k, v in fields.items() if v is not None}})


@app.delete("/api/tasks/{task_id}")
async def remove_task(task_id: int):
    return await mcp.call("delete_task", {"task_id": task_id})


# ---------- Membres ----------

@app.get("/api/members")
async def get_members():
    return await mcp.call("list_members")


@app.post("/api/members", status_code=201)
async def create_member(member: MemberCreate):
    return await mcp.call("create_member", member.model_dump())


@app.patch("/api/members/{member_id}")
async def edit_member(member_id: int, changes: MemberUpdate):
    fields = {k: v for k, v in changes.model_dump(exclude_unset=True).items() if v is not None}
    return await mcp.call("update_member", {"member_id": member_id, **fields})


@app.delete("/api/members/{member_id}")
async def remove_member(member_id: int):
    return await mcp.call("delete_member", {"member_id": member_id})


@app.post("/api/members/{member_id}/merge")
async def merge_members(member_id: int, body: MergeRequest):
    return await mcp.call("merge_members", {"keep_id": member_id, "other_id": body.other_id})


# ---------- Chat multi-agents ----------

@app.post("/api/chat")
async def chat(request: ChatRequest, http_request: Request):
    if not request.question.strip():
        raise HTTPException(400, "La question est vide")
    thread_id = request.thread_id or uuid.uuid4().hex
    try:
        return await ask(http_request.app.state.chat_graph, request.question.strip(), request.language, thread_id)
    except (MCPToolError, LLMNotConfigured):
        raise
    except Exception as error:
        log.exception("Erreur du graphe de chat")
        raise HTTPException(500, f"Erreur de l'assistant : {error}") from error
