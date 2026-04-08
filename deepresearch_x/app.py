from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from deepresearch_x.config import AppSettings
from deepresearch_x.models import ResearchRequest
from deepresearch_x.pipeline import ResearchPipeline


settings = AppSettings()
pipeline = ResearchPipeline.from_settings(settings)

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="DeepResearch-X", version="0.1.0")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "default_loops": settings.default_loops,
            "default_top_k": settings.default_top_k,
            "search_provider": settings.search_provider,
            "llm_provider": settings.llm_provider,
            "default_memory_backend": settings.memory_backend,
            "default_memory_budget_tokens": settings.memory_budget_tokens,
            "default_memory_scope": settings.memory_scope,
        },
    )


@app.post("/api/research", response_class=JSONResponse)
def run_research(payload: ResearchRequest) -> JSONResponse:
    try:
        result = pipeline.run(
            topic=payload.topic,
            loops=payload.loops,
            top_k=payload.top_k,
            session_id=payload.session_id,
            use_memory=payload.use_memory,
            memory_backend=payload.memory_backend,
            memory_budget_tokens=payload.memory_budget_tokens,
            memory_scope=payload.memory_scope,
        )
        return JSONResponse(result.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/sessions/{session_id}", response_class=JSONResponse)
def get_session_checkpoints(session_id: str, memory_backend: str = "") -> JSONResponse:
    try:
        checkpoints = pipeline.get_session_checkpoints(
            session_id=session_id,
            memory_backend=memory_backend,
            limit=20,
        )
        return JSONResponse(
            {
                "session_id": session_id,
                "memory_backend": memory_backend or settings.memory_backend,
                "checkpoints": [c.model_dump() for c in checkpoints],
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/memory/{session_id}", response_class=JSONResponse)
def get_session_memory(
    session_id: str,
    memory_scope: str = "hybrid",
    memory_backend: str = "",
) -> JSONResponse:
    try:
        memories = pipeline.get_session_memory(
            session_id=session_id,
            memory_backend=memory_backend,
            memory_scope=memory_scope,
            limit=40,
        )
        return JSONResponse(
            {
                "session_id": session_id,
                "memory_backend": memory_backend or settings.memory_backend,
                "memory_scope": memory_scope,
                "count": len(memories),
                "items": [m.model_dump() for m in memories],
            }
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
