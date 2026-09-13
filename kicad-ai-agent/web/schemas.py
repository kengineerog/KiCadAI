from typing import Any, Literal

from pydantic import BaseModel, Field


class GoalRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None
    model: str | None = None
    temperature: float = Field(default=0.3, ge=0, le=2)
    project_name: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")


class ModelInfo(BaseModel):
    id: str
    label: str
    provider: str = "OpenAI-compatible"
    available: bool = True


class AgentEvent(BaseModel):
    type: Literal["status", "thought", "tool_call", "tool_result", "artifact", "error", "done"]
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class SessionInfo(BaseModel):
    session_id: str
    model: str
    temperature: float
    kicad: dict[str, Any]
    project: str | None = None


class InstallRequest(BaseModel):
    session_id: str
    component: str
    project_path: str | None = None


class ProjectRequest(BaseModel):
    session_id: str
    project_name: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")
    project_path: str | None = None
