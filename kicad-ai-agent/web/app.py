import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from web.schemas import GoalRequest, InstallRequest, ModelInfo, SessionInfo
from web.session import BASE_DIR, SessionStore

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("kicad-ai-web")

app = FastAPI(title="KiCad AI Control Room", version="0.5.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("WEB_CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
store = SessionStore()
app.mount("/static", StaticFiles(directory=BASE_DIR / "web" / "static"), name="static")


def workspace_path(relative_path: str | Path) -> Path:
    workspace = (BASE_DIR / "workspace").resolve()
    raw_path = Path(relative_path)
    candidate = (raw_path if raw_path.is_absolute() else workspace / raw_path).resolve()
    if workspace != candidate and workspace not in candidate.parents:
        raise HTTPException(status_code=400, detail="Path must stay inside workspace/")
    return candidate


async def configured_models() -> list[ModelInfo]:
    base_url = os.getenv("OMNIROUTE_BASE_URL", "https://api.omniroute.ai").rstrip("/")
    key = os.getenv("OMNIROUTE_KEY")
    if key:
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                response = await client.get(
                    f"{base_url}/models",
                    headers={"Authorization": f"Bearer {key}"},
                )
                response.raise_for_status()
                payload = response.json()
                items = payload.get("data", payload.get("models", []))
                models: list[ModelInfo] = []
                for item in items:
                    if isinstance(item, str):
                        models.append(ModelInfo(id=item, label=item, provider="Omniroute"))
                        continue
                    model_id = item.get("id") or item.get("name")
                    if not model_id:
                        continue
                    provider = item.get("provider") or item.get("owned_by") or item.get("owner") or "Omniroute"
                    models.append(ModelInfo(id=model_id, label=item.get("name") or model_id, provider=str(provider)))
                if models:
                    return models
        except Exception as exc:
            logger.warning("Omniroute model listing unavailable: %s", exc)

    configured = [item.strip() for item in os.getenv("MODEL_OPTIONS", "").split(",") if item.strip()]
    fallback = configured or ["gpt-4o-mini", "claude-3-5-sonnet", "deepseek-chat"]
    current = os.getenv("MODEL_NAME")
    if current and current not in fallback:
        fallback.insert(0, current)
    return [ModelInfo(id=item, label=item, provider="Configured fallback") for item in fallback]


@app.get("/", response_class=HTMLResponse)
async def index():
    return (BASE_DIR / "web" / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "kicad-ai-agent-web"}


@app.get("/api/models", response_model=list[ModelInfo])
async def list_models():
    return await configured_models()


@app.post("/api/run")
async def run_goal(request: GoalRequest, x_session_id: str | None = Header(default=None)):
    session = await store.get_or_create(request.session_id or x_session_id, request.model or os.getenv("MODEL_NAME", "gpt-4o-mini"), request.temperature)
    project_name = request.project_name or f"session_{session.session_id[:8]}"

    async def event_stream():
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def publish(event):
            await queue.put(event)

        async def runner():
            try:
                await session.connect()
                await session.run(request.goal, project_name, event_sink=publish)
            except Exception as exc:
                logger.exception("Agent run failed")
                await queue.put({"type": "error", "message": str(exc), "data": {}})
            finally:
                await queue.put({"type": "done", "message": "Run finished", "data": {"session_id": session.session_id}})
                await queue.put(None)

        task = asyncio.create_task(runner())
        try:
            yield f"event: session\ndata: {json.dumps({'session_id': session.session_id})}\n\n"
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"
            await task
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/session/{session_id}", response_model=SessionInfo)
async def session_info(session_id: str):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    board = await session.kicad.get_board_info()
    return SessionInfo(session_id=session.session_id, model=session.model, temperature=session.temperature, kicad=board, project=session.current_project)


@app.get("/api/artifacts")
async def artifacts(session_id: str = Query(...)):
    session = store.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    items = list(session.artifacts)
    if session.current_project:
        project_dir = BASE_DIR / "workspace" / "projects" / session.current_project
        if project_dir.exists():
            known = {item["path"] for item in items}
            for path in project_dir.rglob("*"):
                if path.is_file():
                    relative = str(path.relative_to(BASE_DIR / "workspace"))
                    if relative not in known:
                        items.append({"name": path.name, "path": relative, "kind": "project"})
    return {"session_id": session_id, "artifacts": items}


@app.get("/api/download/{file_path:path}")
async def download(file_path: str):
    path = workspace_path(file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path, filename=path.name)


@app.post("/api/install-library")
async def install_library(request: InstallRequest):
    session = store.get(request.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    project_path = request.project_path or str(BASE_DIR / "workspace" / "projects" / (session.current_project or "default"))
    safe_project_path = workspace_path(project_path)
    return session.generator.install_project_library(safe_project_path, request.component)
