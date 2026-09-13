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

The API includes `GET /api/models`, `POST /api/run` (SSE), `POST /api/stop/{session_id}`, `GET /api/session/{session_id}`, `GET /api/projects`, project open/save/close routes, `GET /api/artifacts`, `GET /api/download/{path}`, and `POST /api/install-library`.

### Phase 6 practical workflow

Use the **ATmega + LED blink** quick action, or submit a goal such as:

```text
Create a simple project with an ATmega328P and an LED that can flash.
Generate any missing symbols/footprints, create the project, place the
components, and connect power, ground, and the LED with a current-limiting resistor.
```

The planner detects common parts, searches and caches a datasheet result, extracts pin/package data, generates symbol/footprint/evidence files, installs them into the project library, adds schematic symbols and PCB footprints, and records requested logical nets. Without Omniroute or a live KiCad IPC connection, the same flow runs in explicit mock/development mode and reports that mode in the live stream.
