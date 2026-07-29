from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


Priority = Literal["P0", "P1", "P2"]
RequirementStatus = Literal["draft", "confirmed", "rejected"]
Stage = Literal["discover", "clarify", "specify", "plan", "design", "review", "ready"]


class FunctionalRequirement(BaseModel):
    id: str
    title: str
    description: str = ""
    priority: Priority = "P1"
    acceptance_criteria: list[str] = Field(default_factory=list)
    status: RequirementStatus = "draft"


class NonFunctionalRequirement(BaseModel):
    category: str
    requirement: str
    target: str = ""
    priority: Priority = "P1"
    status: RequirementStatus = "draft"


class DataEntity(BaseModel):
    name: str
    purpose: str = ""
    key_fields: list[str] = Field(default_factory=list)
    sensitive: bool = False


class Integration(BaseModel):
    name: str
    purpose: str = ""
    protocol: str = ""
    status: RequirementStatus = "draft"


class Decision(BaseModel):
    id: str
    topic: str
    decision: str
    rationale: str = ""
    status: Literal["proposed", "confirmed"] = "proposed"


class OpenQuestion(BaseModel):
    id: str
    question: str
    category: str = "general"
    importance: Literal["blocking", "important", "optional"] = "important"
    status: Literal["open", "answered", "deferred"] = "open"
    answer: str = ""


class Risk(BaseModel):
    title: str
    impact: str = ""
    mitigation: str = ""


class ArchitectureChoice(BaseModel):
    style: str = ""
    frontend: str = ""
    backend: str = ""
    database: str = ""
    infrastructure: str = ""
    authentication: str = ""


class Requirements(BaseModel):
    project_name: str = ""
    summary: str = ""
    purpose: str = ""
    background: str = ""
    target_users: list[str] = Field(default_factory=list)
    stakeholders: list[str] = Field(default_factory=list)
    user_stories: list[str] = Field(default_factory=list)
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)
    functional_requirements: list[FunctionalRequirement] = Field(default_factory=list)
    non_functional_requirements: list[NonFunctionalRequirement] = Field(default_factory=list)
    data_entities: list[DataEntity] = Field(default_factory=list)
    integrations: list[Integration] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    decisions: list[Decision] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    architecture: ArchitectureChoice = Field(default_factory=ArchitectureChoice)
    raw_notes: list[str] = Field(default_factory=list)
    stage: Stage = "discover"
    revision: int = 1


class ChatTurnOutput(BaseModel):
    assistant_message: str
    requirements: Requirements
    next_questions: list[str] = Field(default_factory=list, max_length=3)
    changed_summary: list[str] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    initial_idea: str = Field(default="", max_length=5000)
    model: str = Field(default="")


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)


class Message(BaseModel):
    id: int
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: str


class ProjectSummary(BaseModel):
    id: str
    name: str
    stage: Stage
    completeness: int
    model: str
    created_at: str
    updated_at: str


class ProjectDetail(ProjectSummary):
    initial_idea: str
    requirements: Requirements
    messages: list[Message]
    document_markdown: str
    llm_warning: str = ""


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")

