"""Local operator workbench API and static application."""

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from .adapters import normalize
from .db import Database
from .ml import load_predictor
from .schemas import Review
from .service import Conflict, Workbench


def create_app(runtime=None):
    root = Path(runtime or os.environ.get("SMT_RUNTIME", "runtime")).resolve()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    model_path = root / "model.joblib"
    predictor = load_predictor(model_path) if model_path.exists() else None
    service = Workbench(Database(root / "workbench.db"), artifacts, predictor)
    app = FastAPI(title="SMT Central Verification Workbench", version="0.1.0")
    app.state.service = service

    @app.exception_handler(Conflict)
    async def conflict_handler(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "model_loaded": service.predictor is not None, "synthetic_only": True}

    @app.get("/api/state")
    def state(run_id: str | None = None):
        return service.snapshot(run_id)

    @app.get("/api/model")
    def model():
        report = root / "model.json"
        return json.loads(report.read_text()) if report.exists() else {"status": "not_trained"}

    @app.post("/api/events")
    async def ingest(request: Request):
        try:
            message = await request.json()
            if not isinstance(message, dict):
                raise TypeError("event must be an object")
            result = service.ingest(normalize(message))
        except (ValidationError, ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, Conflict):
                raise
            raise HTTPException(422, detail=str(exc)) from exc
        return JSONResponse(status_code=202 if result["status"] == "quarantined" else 200, content=result)

    @app.post("/api/replay")
    def replay():
        return {"results": service.replay()}

    @app.post("/api/boards/{run_id}/{board_id}/review")
    def review(run_id: str, board_id: str, body: Review):
        return service.review(run_id, board_id, body)

    app.mount("/artifacts", StaticFiles(directory=artifacts), name="artifacts")
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")
    return app
