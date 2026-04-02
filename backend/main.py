"""FastAPI application — Schedule Forensics Tool.

All processing is local-only; no data leaves the machine.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.session import session_manager

logger = logging.getLogger(__name__)

MAX_FILES_PER_SESSION = 10
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: start JVM + session sweep. Shutdown: cancel sweep."""
    # Configure session manager
    session_manager.configure(upload_dir=UPLOAD_DIR, ttl_hours=4.0)

    # Start JVM for MPXJ (best-effort; sets JVM_AVAILABLE flag)
    try:
        from backend.parser import mpp_parser
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, mpp_parser.start_jvm)
    except Exception as exc:
        logger.warning("JVM startup skipped: %s", exc)

    # Start background session sweep
    await session_manager.start_sweep_task()
    logger.info("Schedule Forensics API started")

    yield

    # Shutdown
    await session_manager.stop_sweep_task()
    logger.info("Schedule Forensics API stopped")


app = FastAPI(
    title="Schedule Forensics Tool",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/response models ───────────────────────────────────────────────────


class AnalyzeRequest(BaseModel):
    version_index: int


class DiffRequest(BaseModel):
    base_index: int
    compare_index: int


class ForensicsRequest(BaseModel):
    version_indices: list[int]


class ChatRequest(BaseModel):
    query: str


# ── Helper ────────────────────────────────────────────────────────────────────


def _require_session(session_id: str):
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return session


def _get_cpm(session_id: str, version_index: int):
    """Return cached CPM result, computing if needed."""
    cache_key = f"cpm_{version_index}"
    cached = session_manager.cache_get(session_id, cache_key)
    if cached is not None:
        return cached

    versions = session_manager.get_versions(session_id)
    version = next((v for v in versions if v.version_index == version_index), None)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version {version_index} not found")

    from backend.analysis.cpm import run_cpm
    result = run_cpm(version)
    session_manager.cache_set(session_id, cache_key, result)
    return result


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.post("/session/create")
async def create_session() -> dict[str, Any]:
    """Create a new analysis session."""
    session = session_manager.create_session()
    return {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
    }


@app.post("/session/{session_id}/upload")
async def upload_files(
    session_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    """Upload one or more .mpp files (max 10 per session)."""
    _require_session(session_id)

    existing = session_manager.get_versions(session_id)
    if len(existing) + len(files) > MAX_FILES_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Too many files. Max {MAX_FILES_PER_SESSION} per session.",
        )

    upload_path = session_manager.session_upload_path(session_id)
    results = []

    from backend.parser import mpp_parser

    for i, upload in enumerate(files):
        filename = upload.filename or f"upload_{i}.mpp"

        # Validate extension
        if not filename.lower().endswith(".mpp"):
            results.append({"filename": filename, "status": "skipped", "reason": "Not a .mpp file"})
            continue

        # Save to disk
        dest = upload_path / filename
        content = await upload.read()
        dest.write_bytes(content)

        # Parse
        version_index = len(existing) + len(results)
        try:
            loop = asyncio.get_event_loop()
            parsed_dict = await loop.run_in_executor(
                None, mpp_parser.parse_mpp, str(dest), version_index
            )
            from backend.models.schemas import ScheduleVersion
            version = ScheduleVersion(**parsed_dict)
            session_manager.add_version(session_id, version)
            results.append({
                "filename": filename,
                "status": "ok",
                "version_index": version_index,
                "task_count": len(version.tasks),
                "link_count": len(version.links),
                "status_date": version.status_date.isoformat() if version.status_date else None,
            })
        except mpp_parser.ScheduleParseError as exc:
            dest.unlink(missing_ok=True)
            results.append({"filename": filename, "status": "error", "reason": str(exc)})
        except Exception as exc:
            dest.unlink(missing_ok=True)
            results.append({"filename": filename, "status": "error", "reason": f"Unexpected error: {exc}"})

    return {"session_id": session_id, "uploaded": results}


@app.get("/session/{session_id}/versions")
async def get_versions(session_id: str) -> dict[str, Any]:
    """List all loaded versions in the session."""
    _require_session(session_id)
    versions = session_manager.get_versions(session_id)
    return {
        "session_id": session_id,
        "versions": [
            {
                "version_index": v.version_index,
                "filename": v.filename,
                "status_date": v.status_date.isoformat() if v.status_date else None,
                "project_start": v.project_start.isoformat() if v.project_start else None,
                "project_finish": v.project_finish.isoformat() if v.project_finish else None,
                "task_count": len(v.tasks),
                "link_count": len(v.links),
            }
            for v in versions
        ],
    }


@app.post("/session/{session_id}/analyze")
async def analyze_version(session_id: str, req: AnalyzeRequest) -> dict[str, Any]:
    """Run CPM analysis on a specific version."""
    _require_session(session_id)
    cpm = _get_cpm(session_id, req.version_index)
    return {
        "session_id": session_id,
        "version_index": req.version_index,
        "has_cycles": cpm.has_cycles,
        "cycle_tasks": cpm.cycle_tasks,
        "critical_path": cpm.critical_path,
        "near_critical": cpm.near_critical,
        "project_duration_days": cpm.project_duration_days,
        "task_floats": {
            uid: {
                "total_float": tf.total_float,
                "free_float": tf.free_float,
                "is_critical": tf.is_critical,
                "is_near_critical": tf.is_near_critical,
            }
            for uid, tf in cpm.task_floats.items()
        },
    }


@app.post("/session/{session_id}/diff")
async def diff_versions_endpoint(session_id: str, req: DiffRequest) -> dict[str, Any]:
    """Diff two schedule versions."""
    _require_session(session_id)
    versions = session_manager.get_versions(session_id)

    base_v = next((v for v in versions if v.version_index == req.base_index), None)
    cmp_v = next((v for v in versions if v.version_index == req.compare_index), None)

    if base_v is None:
        raise HTTPException(status_code=404, detail=f"Base version {req.base_index} not found")
    if cmp_v is None:
        raise HTTPException(status_code=404, detail=f"Compare version {req.compare_index} not found")

    cache_key = f"diff_{req.base_index}_{req.compare_index}"
    cached = session_manager.cache_get(session_id, cache_key)
    if cached is not None:
        return cached

    base_cpm = _get_cpm(session_id, req.base_index)
    cmp_cpm = _get_cpm(session_id, req.compare_index)

    from backend.analysis.diff_engine import diff_versions
    diff = diff_versions(base_v, cmp_v, base_cpm, cmp_cpm)

    result = {
        "session_id": session_id,
        "base_version_index": diff.base_version_index,
        "compare_version_index": diff.compare_version_index,
        "project_finish_delta_days": diff.project_finish_delta_days,
        "critical_path_length_delta": diff.critical_path_length_delta,
        "new_critical_task_count": diff.new_critical_task_count,
        "removed_critical_task_count": diff.removed_critical_task_count,
        "task_changes": [c.model_dump() for c in diff.task_changes],
        "link_changes": [c.model_dump() for c in diff.link_changes],
    }
    session_manager.cache_set(session_id, cache_key, result)
    return result


@app.get("/session/{session_id}/dcma/{version_index}")
async def get_dcma(session_id: str, version_index: int) -> dict[str, Any]:
    """Run DCMA 14-point check on a version."""
    _require_session(session_id)

    cache_key = f"dcma_{version_index}"
    cached = session_manager.cache_get(session_id, cache_key)
    if cached is not None:
        return cached

    versions = session_manager.get_versions(session_id)
    version = next((v for v in versions if v.version_index == version_index), None)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version {version_index} not found")

    cpm = _get_cpm(session_id, version_index)

    from backend.analysis.dcma import compute_dcma
    result = compute_dcma(version, cpm)

    out = {
        "session_id": session_id,
        "version_index": version_index,
        "overall_status": result.overall_status,
        "metrics": [m.model_dump() for m in result.metrics],
    }
    session_manager.cache_set(session_id, cache_key, out)
    return out


@app.post("/session/{session_id}/forensics")
async def run_forensics(session_id: str, req: ForensicsRequest) -> dict[str, Any]:
    """Run forensic manipulation detection across selected versions."""
    _require_session(session_id)

    all_versions = session_manager.get_versions(session_id)
    selected = [v for v in all_versions if v.version_index in req.version_indices]

    if not selected:
        raise HTTPException(status_code=400, detail="No matching versions found")

    cache_key = f"forensics_{'_'.join(str(i) for i in sorted(req.version_indices))}"
    cached = session_manager.cache_get(session_id, cache_key)
    if cached is not None:
        return cached

    from backend.analysis.forensics import detect_all_patterns
    result = detect_all_patterns(selected)

    out = {
        "session_id": session_id,
        "version_indices": result.version_indices,
        "manipulation_risk_score": result.manipulation_risk_score,
        "findings": [f.model_dump() for f in result.findings],
    }
    session_manager.cache_set(session_id, cache_key, out)
    return out


@app.post("/session/{session_id}/chat")
async def chat(session_id: str, req: ChatRequest) -> dict[str, Any]:
    """Route a natural-language schedule query."""
    _require_session(session_id)

    versions = session_manager.get_versions(session_id)

    # Load cached analysis results if available
    cpm_results = {}
    for v in versions:
        cached_cpm = session_manager.cache_get(session_id, f"cpm_{v.version_index}")
        if cached_cpm is not None:
            cpm_results[v.version_index] = cached_cpm

    dcma_results = {}
    for v in versions:
        cached_dcma = session_manager.cache_get(session_id, f"dcma_{v.version_index}")
        if cached_dcma is not None:
            dcma_results[v.version_index] = cached_dcma

    forensics_result = session_manager.cache_get(session_id, "forensics_latest")

    from backend.chat.intent_router import route_query
    response = route_query(
        query=req.query,
        versions=versions,
        cpm_results=cpm_results if cpm_results else None,
        dcma_results=dcma_results if dcma_results else None,
        forensics_result=forensics_result,
    )

    return {"session_id": session_id, **response}


@app.delete("/session/{session_id}/end")
async def end_session(session_id: str) -> dict[str, Any]:
    """Immediately wipe all session data (files + in-memory state)."""
    destroyed = await session_manager.end_session(session_id)
    if not destroyed:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")
    return {"session_id": session_id, "status": "destroyed"}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check."""
    from backend.parser import mpp_parser
    return {
        "status": "ok",
        "jvm_available": str(mpp_parser.JVM_AVAILABLE),
    }
