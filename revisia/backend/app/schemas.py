"""Schémas Pydantic : sorties structurées du LLM et corps des requêtes de l'API."""
from typing import Literal

from pydantic import BaseModel, Field, field_validator

AgentName = Literal["tutor", "navigator", "quizmaster"]


def _clean_strings(value):
    return list(dict.fromkeys(str(v).strip() for v in (value or []) if str(v).strip()))


# ---------- Sorties du LLM ----------

class Concept(BaseModel):
    name: str
    definition: str = ""


class ChapterAnalysis(BaseModel):
    title: str = ""
    summary: str = ""
    concepts: list[Concept] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)

    @field_validator("skills", "prerequisites", mode="before")
    @classmethod
    def _strings(cls, value):
        return _clean_strings(value)

    @field_validator("concepts", mode="before")
    @classmethod
    def _concepts(cls, value):
        items = []
        for item in value or []:
            if isinstance(item, str):
                item = {"name": item}
            if isinstance(item, dict) and str(item.get("name", "")).strip():
                items.append(item)
        return items


class QuizQuestion(BaseModel):
    question: str
    choices: list[str]
    answer_index: int = 0
    explanation: str = ""

    @field_validator("answer_index")
    @classmethod
    def _in_range(cls, value, info):
        choices = info.data.get("choices") or []
        return value if 0 <= value < max(len(choices), 1) else 0


class CourseMaterial(BaseModel):
    summary: str = ""
    key_concepts: list[dict] = Field(default_factory=list)
    quiz: list[QuizQuestion] = Field(default_factory=list)


class Quiz(BaseModel):
    quiz: list[QuizQuestion] = Field(default_factory=list)


class LinkDecision(BaseModel):
    chapter_id: int
    prerequisite_chapter_id: int
    reason: str = ""


class LinkDecisions(BaseModel):
    links: list[LinkDecision] = Field(default_factory=list)


class Route(BaseModel):
    agents: list[AgentName] = Field(default_factory=list)
    reasoning: str = ""

    @field_validator("agents", mode="before")
    @classmethod
    def _known(cls, value):
        return [a for a in _clean_strings(value) if a in {"tutor", "navigator", "quizmaster"}]


# ---------- Requêtes de l'API ----------

class PositionUpdate(BaseModel):
    position: int = Field(ge=1)


class DependencyCreate(BaseModel):
    chapter_id: int
    prerequisite_chapter_id: int
    reason: str = ""


class ChatRequest(BaseModel):
    question: str
    course_id: int | None = None
    language: Literal["fr", "en"] = "fr"
    thread_id: str | None = None
