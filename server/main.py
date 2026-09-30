"""FastAPI application: REST + WebSocket API and static UI serving."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .dag import Dag
from .events import BUS
from .executor import EXECUTOR
from .planner import plan_dag
from .workspace import Workspace

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# In-memory registry of runs (single-user studio; swap for a DB to scale)
RUNS: dict[str, Dag] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await BUS.publish("server.started", port=8000)
    yield


app = FastAPI(title="Dynamic DAG Multi-Agent Studio", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------- REST
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "runs": len(RUNS)}


@app.post("/api/run")
async def create_run(payload: dict) -> JSONResponse:
    query = (payload.get("query") or "").strip()
    if not query:
        return JSONResponse({"error": "query is required"}, status_code=400)
    if EXECUTOR.running:
        return JSONResponse({"error": "a run is already in progress"}, status_code=409)

    dag = await plan_dag(query)
    RUNS[dag.id] = dag
    asyncio.create_task(EXECUTOR.run(dag))
    return JSONResponse({"run_id": dag.id, "dag": dag.to_dict()})


@app.post("/api/run/{run_id}/cancel")
async def cancel_run(run_id: str) -> JSONResponse:
    EXECUTOR.cancel()
    return JSONResponse({"run_id": run_id, "cancelling": True})


@app.get("/api/run/{run_id}")
async def get_run(run_id: str) -> JSONResponse:
    dag = RUNS.get(run_id)
    if not dag:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    return JSONResponse(dag.to_dict())


@app.get("/api/run/{run_id}/files")
async def list_files(run_id: str) -> JSONResponse:
    if run_id not in RUNS:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    return JSONResponse({"files": Workspace(run_id).list_files()})


@app.get("/api/run/{run_id}/file")
async def read_file(run_id: str, path: str) -> JSONResponse:
    if run_id not in RUNS:
        return JSONResponse({"error": "unknown run"}, status_code=404)
    try:
        content = Workspace(run_id).read(path)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return JSONResponse({"path": path, "content": content})


# ---------------------------------------------------------------- WebSocket
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    q = BUS.subscribe()
    try:
        # Send the event history so late joiners can render the current state
        for event in BUS.snapshot():
            await ws.send_text(json.dumps(event))
        while True:
            try:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=0.2)
            except asyncio.TimeoutError:
                # Drain queued events while idle
                while not q.empty():
                    await ws.send_text(json.dumps(q.get_nowait()))
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    finally:
        BUS.unsubscribe(q)


# ------------------------------------------------------------------ static
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
