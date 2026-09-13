import asyncio
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent.model import ModelClient, ModelConfig
from agent.planner import AgentPlanner
from agent.tool_registry import ToolRegistry
from mcp_servers.kicad_mcp import KiCadMCP
from mcp_servers.research_mcp import ResearchMCP
from tools.component.component_generator import ComponentGenerator


BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass
class AgentSession:
    session_id: str
    model: str
    temperature: float
    events: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    current_project: str | None = None
    running: bool = False

    def __post_init__(self):
        self.research = ResearchMCP(
            os.getenv("OMNIROUTE_KEY"),
            os.getenv("OMNIROUTE_BASE_URL", "https://api.omniroute.ai"),
            BASE_DIR / "workspace" / "research_cache" / self.session_id,
        )
        self.kicad = KiCadMCP(BASE_DIR / "workspace" / "projects")
        self.generator = ComponentGenerator(BASE_DIR / "workspace" / "libraries" / "custom")
        self.registry = ToolRegistry(BASE_DIR / "tools")
        self.planner = AgentPlanner(self.registry, self.research, self.kicad, self.generator)
        self.model_client = ModelClient(
            ModelConfig(
                base_url=os.getenv("MODEL_BASE_URL", "http://localhost:8000/v1"),
                api_key=os.getenv("MODEL_API_KEY", "test-key"),
                model=self.model,
                temperature=self.temperature,
            )
        )
        self._lock = asyncio.Lock()

    async def connect(self) -> dict[str, Any]:
        return await self.kicad.connect()

    async def close(self):
        await self.research.__aexit__(None, None, None)
        await self.model_client.close()

    async def record(self, event: dict[str, Any]):
        self.events.append(event)
        if event["type"] == "artifact":
            data = event.get("data", {})
            for key in ("symbol_file", "footprint_file", "evidence_file"):
                if data.get(key):
                    path = Path(data[key])
                    try:
                        relative = path.resolve().relative_to(BASE_DIR / "workspace")
                    except ValueError:
                        relative = path
                    self.artifacts.append({"name": path.name, "path": str(relative), "kind": key})
        if getattr(self, "_event_sink", None):
            await self._event_sink(event)

    async def run(self, goal: str, project_name: str, event_sink=None):
        async with self._lock:
            if self.running:
                raise RuntimeError("This session is already running")
            self.running = True
            self.events.clear()
            self.artifacts.clear()
            self.current_project = project_name
            self._event_sink = event_sink
            await self.connect()
            try:
                await self.record({"type": "thought", "message": "Goal accepted", "data": {"session_id": self.session_id}})
                await self.planner.execute(
                    goal,
                    project_name=project_name,
                    project_root=BASE_DIR / "workspace" / "projects",
                    event_callback=self.record,
                )
            finally:
                self._event_sink = None
                self.running = False


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str | None, model: str, temperature: float) -> AgentSession:
        async with self._lock:
            key = session_id or str(uuid.uuid4())
            if key not in self._sessions:
                self._sessions[key] = AgentSession(key, model, temperature)
            else:
                self._sessions[key].model = model
                self._sessions[key].temperature = temperature
                self._sessions[key].model_client.config.model = model
                self._sessions[key].model_client.config.temperature = temperature
            return self._sessions[key]

    def get(self, session_id: str) -> AgentSession | None:
        return self._sessions.get(session_id)
