"""API FastAPI de RecrutIA.

Le backend ne lit jamais directement les CV ni la base : chaque route passe par le client MCP.
"""
import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import agent, recruiting
from .config import GROQ_API_KEY
from .mcp_client import mcp_client


@asynccontextmanager
async def lifespan(app):
    # Au démarrage, on lance le serveur MCP ; à l'arrêt, on le ferme
    await mcp_client.start()
    yield
    await mcp_client.stop()


app = FastAPI(title="RecrutIA - Assistant RH", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5175", "http://127.0.0.1:5175"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobCreate(BaseModel):
    title: str
    description: str
    skills: str = ""


class StatusUpdate(BaseModel):
    status: str


class NoteCreate(BaseModel):
    note: str


class OutreachRequest(BaseModel):
    candidate_id: int
    job_id: int
    channel: str = "email"
    language: str = "fr"
    recruiter: str = ""
    company: str = ""


class AgentRequest(BaseModel):
    messages: list[dict]


async def call_tool(name, arguments=None):
    """Appelle un outil MCP et transforme ses erreurs en erreurs HTTP."""
    result = await mcp_client.call(name, arguments)
    if isinstance(result, dict) and "error" in result:
        raise HTTPException(400, result["error"])
    return result


@app.get("/api/health")
async def health():
    tools = await mcp_client.list_tools()
    return {"status": "ok", "groq_key_configured": bool(GROQ_API_KEY), "mcp_tools": len(tools)}


@app.get("/api/tools")
async def list_mcp_tools():
    """Les outils exposés par le serveur MCP (affichés dans l'interface)."""
    return [
        {"name": t.name, "description": t.description, "agent_allowed": t.name in agent.AGENT_ALLOWED_TOOLS}
        for t in await mcp_client.list_tools()
    ]


@app.get("/api/stats")
async def stats():
    return await call_tool("pipeline_stats")


# ---------- Candidats ----------

@app.get("/api/candidates")
async def list_candidates(status: str = ""):
    return await call_tool("list_candidates", {"status": status})


@app.get("/api/candidates/{candidate_id}")
async def get_candidate(candidate_id: int):
    return await call_tool("read_cv", {"candidate_id": candidate_id})


@app.post("/api/candidates")
async def upload_cvs(files: list[UploadFile] = File(...)):
    added, errors = [], []
    for file in files:
        content = base64.b64encode(await file.read()).decode()
        result = await mcp_client.call("upload_cv", {"filename": file.filename, "content_base64": content})
        if "error" in result:
            errors.append(result["error"])
        else:
            added += result["added"]
    return {"added": added, "errors": errors}


@app.post("/api/candidates/import")
async def import_from_folder():
    """Importe les CV déposés directement dans le dossier data/cvs."""
    return await call_tool("import_cvs")


@app.patch("/api/candidates/{candidate_id}/status")
async def update_status(candidate_id: int, body: StatusUpdate):
    return await call_tool("update_candidate_status", {"candidate_id": candidate_id, "status": body.status})


@app.post("/api/candidates/{candidate_id}/notes")
async def add_note(candidate_id: int, body: NoteCreate):
    if not body.note.strip():
        raise HTTPException(400, "La note est vide")
    return await call_tool("add_candidate_note", {"candidate_id": candidate_id, "note": body.note.strip()})


@app.delete("/api/candidates/{candidate_id}")
async def delete_candidate(candidate_id: int):
    return await call_tool("delete_candidate", {"candidate_id": candidate_id})


# ---------- Postes ----------

@app.get("/api/jobs")
async def list_jobs():
    return await call_tool("list_jobs")


@app.post("/api/jobs")
async def create_job(job: JobCreate):
    if not job.title.strip() or not job.description.strip():
        raise HTTPException(400, "Le titre et la description sont obligatoires")
    return await call_tool("create_job", job.model_dump())


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int):
    return await call_tool("get_job", {"job_id": job_id})


@app.delete("/api/jobs/{job_id}")
async def delete_job(job_id: int):
    return await call_tool("delete_job", {"job_id": job_id})


# ---------- IA ----------

@app.post("/api/jobs/{job_id}/match")
async def match(job_id: int):
    try:
        return await recruiting.match_candidates(job_id)
    except Exception as error:
        raise HTTPException(500, str(error))


@app.post("/api/outreach")
async def outreach(body: OutreachRequest):
    try:
        message = await recruiting.write_outreach(**body.model_dump())
        return {"message": message}
    except Exception as error:
        raise HTTPException(500, str(error))


@app.post("/api/agent")
async def ask_agent(body: AgentRequest):
    history = [m for m in body.messages if m.get("role") in ("user", "assistant") and m.get("content")]
    if not history:
        raise HTTPException(400, "Aucun message")
    try:
        return await agent.run_agent(history)
    except Exception as error:
        raise HTTPException(500, str(error))
