"""Schémas Pydantic : sorties structurées du LLM et corps des requêtes de l'API."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AgentName = Literal["historian", "task_manager", "analyst"]


# ---------- Sorties du LLM ----------

class ExtractedTask(BaseModel):
    description: str = ""
    assignee: str | None = None
    due_date: str | None = None


class MeetingExtraction(BaseModel):
    summary: str = ""
    decisions: list[str] = Field(default_factory=list)
    tasks: list[ExtractedTask] = Field(default_factory=list)

    @field_validator("decisions", mode="before")
    @classmethod
    def _strings_only(cls, value):
        return [str(v).strip() for v in (value or []) if str(v).strip()]


class MergedSummary(BaseModel):
    summary: str
    decisions: list[str] = Field(default_factory=list)


class Route(BaseModel):
    agents: list[AgentName] = Field(default_factory=list)
    reasoning: str = ""

    @field_validator("agents", mode="before")
    @classmethod
    def _known_agents(cls, value):
        allowed = {"historian", "task_manager", "analyst"}
        return list(dict.fromkeys(a for a in (value or []) if a in allowed))


# ---------- Requêtes de l'API ----------

class TaskCreate(BaseModel):
    description: str
    assignee: str = ""
    due_date: str | None = None
    meeting_id: int | None = None


class TaskUpdate(BaseModel):
    description: str | None = None
    assignee: str | None = None
    due_date: str | None = None
    status: Literal["a_faire", "en_cours", "termine"] | None = None


class MemberCreate(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    email: str = ""


class MemberUpdate(BaseModel):
    name: str | None = None
    aliases: list[str] | None = None
    email: str | None = None


class MergeRequest(BaseModel):
    other_id: int


class ChatRequest(BaseModel):
    question: str
    language: Literal["fr", "en"] = "fr"
    # Identifiant de conversation : la mémoire LangGraph garde le fil entre les questions
    thread_id: str | None = None
