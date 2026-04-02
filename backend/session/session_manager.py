"""Session manager — upload handling, TTL wipe, in-memory session state."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from backend.models.schemas import Session, ScheduleVersion

logger = logging.getLogger(__name__)

# In-process session store: session_id -> Session
_sessions: dict[str, Session] = {}

# Directory for uploaded files (created on startup)
_upload_dir: Path = Path("./uploads")

# TTL for sessions (default 4 hours)
_session_ttl_hours: float = 4.0

_sweep_task: Optional[asyncio.Task] = None


def configure(upload_dir: str = "./uploads", ttl_hours: float = 4.0) -> None:
    """Configure the session manager. Call once at startup."""
    global _upload_dir, _session_ttl_hours
    _upload_dir = Path(upload_dir)
    _upload_dir.mkdir(parents=True, exist_ok=True)
    _session_ttl_hours = ttl_hours


async def start_sweep_task() -> None:
    """Start the background TTL sweep task."""
    global _sweep_task
    if _sweep_task is None or _sweep_task.done():
        _sweep_task = asyncio.create_task(_sweep_expired_sessions())


async def stop_sweep_task() -> None:
    """Cancel the background sweep task."""
    if _sweep_task and not _sweep_task.done():
        _sweep_task.cancel()
        try:
            await _sweep_task
        except asyncio.CancelledError:
            pass


# ── Session lifecycle ─────────────────────────────────────────────────────────


def create_session() -> Session:
    """Create a new session and return it."""
    now = datetime.utcnow()
    session = Session(
        session_id=str(uuid.uuid4()),
        created_at=now,
        expires_at=now + timedelta(hours=_session_ttl_hours),
        versions=[],
        upload_paths=[],
    )
    _sessions[session.session_id] = session
    session_upload_dir = _upload_dir / session.session_id
    session_upload_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Session created: %s", session.session_id)
    return session


def get_session(session_id: str) -> Optional[Session]:
    """Return the session or None if not found / expired."""
    session = _sessions.get(session_id)
    if session is None:
        return None
    if datetime.utcnow() > session.expires_at:
        asyncio.create_task(_destroy_session(session_id))
        return None
    return session


async def end_session(session_id: str) -> bool:
    """Immediately wipe all data for a session.

    Returns True if session existed and was destroyed.
    """
    if session_id not in _sessions:
        return False
    await _destroy_session(session_id)
    return True


def add_version(session_id: str, version: ScheduleVersion) -> None:
    """Append a parsed schedule version to the session."""
    session = _sessions.get(session_id)
    if session is None:
        raise KeyError(f"Session not found: {session_id}")
    session.versions.append(version)


def get_versions(session_id: str) -> list[ScheduleVersion]:
    session = get_session(session_id)
    if session is None:
        return []
    return session.versions


def session_upload_path(session_id: str) -> Path:
    return _upload_dir / session_id


# ── Analysis cache ────────────────────────────────────────────────────────────

_analysis_cache: dict[str, dict[str, Any]] = {}  # session_id -> {key: result}


def cache_set(session_id: str, key: str, value: Any) -> None:
    if session_id not in _analysis_cache:
        _analysis_cache[session_id] = {}
    _analysis_cache[session_id][key] = value


def cache_get(session_id: str, key: str) -> Optional[Any]:
    return _analysis_cache.get(session_id, {}).get(key)


# ── Wipe logic ────────────────────────────────────────────────────────────────


async def _destroy_session(session_id: str) -> None:
    """Delete all files and state for a session."""
    # Remove from session store
    session = _sessions.pop(session_id, None)

    # Remove from analysis cache
    _analysis_cache.pop(session_id, None)

    # Delete uploaded files
    upload_dir = _upload_dir / session_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    logger.info("Session destroyed: %s", session_id)


async def _sweep_expired_sessions() -> None:
    """Periodically sweep and destroy expired sessions."""
    sweep_interval = 300  # 5 minutes
    while True:
        try:
            await asyncio.sleep(sweep_interval)
            now = datetime.utcnow()
            expired = [sid for sid, s in list(_sessions.items()) if now > s.expires_at]
            for sid in expired:
                logger.info("Expiring session: %s", sid)
                await _destroy_session(sid)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in session sweep: %s", exc)
