# KiCad AI Agent

## Web control room

The Phase 5 web UI exposes model selection, goal submission, live agent events, generated artifacts, and KiCad status through a small FastAPI application. It reuses the existing `AgentPlanner`, `ResearchMCP`, `ComponentGenerator`, `KiCadMCP`, and `ToolRegistry`.

From the project directory:

```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
uvicorn web.app:app --reload --host 0.0.0.0 --port 8000
```

Open http://localhost:8000/.

The UI works without an Omniroute key or a running KiCad instance. In that mode the research adapter returns mock results and KiCad reports development-fallback status. Optional configuration is read from `.env`:

- `OMNIROUTE_KEY` and `OMNIROUTE_BASE_URL`
- `MODEL_BASE_URL`, `MODEL_API_KEY`, and `MODEL_NAME`
- `MODEL_OPTIONS` as a comma-separated fallback model list
- `WEB_CORS_ORIGINS` as a comma-separated origin list

The API includes `GET /api/models`, `POST /api/run` (SSE), `GET /api/session/{session_id}`, `GET /api/artifacts`, `GET /api/download/{path}`, and `POST /api/install-library`.
