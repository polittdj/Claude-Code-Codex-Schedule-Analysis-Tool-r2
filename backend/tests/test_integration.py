"""Integration tests for the FastAPI backend — session lifecycle, analysis endpoints, chat."""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.session import session_manager
from backend.tests.synthetic.schedule_factory import (
    forensics_multi_version,
    simple_linear_schedule,
    parallel_path_schedule,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def reset_session_store():
    """Clear session state before each test."""
    session_manager._sessions.clear()
    session_manager._analysis_cache.clear()
    session_manager.configure(upload_dir="/tmp/test_uploads", ttl_hours=4.0)
    yield
    session_manager._sessions.clear()
    session_manager._analysis_cache.clear()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session_with_versions(client):
    """Create a session and load two synthetic versions via session_manager directly."""
    # Create session via API
    resp = await client.post("/session/create")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    # Add versions directly (bypassing file upload — no JVM needed for tests)
    v0 = simple_linear_schedule(version_index=0)
    v1 = parallel_path_schedule(version_index=1)
    session_manager.add_version(session_id, v0)
    session_manager.add_version(session_id, v1)

    return session_id, [v0, v1]


# ── Session lifecycle ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_session(client):
    resp = await client.post("/session/create")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert "created_at" in data
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_end_session(client):
    # Create
    resp = await client.post("/session/create")
    session_id = resp.json()["session_id"]

    # End
    resp = await client.delete(f"/session/{session_id}/end")
    assert resp.status_code == 200
    assert resp.json()["status"] == "destroyed"

    # Second end should 404
    resp = await client.delete(f"/session/{session_id}/end")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_end_nonexistent_session(client):
    resp = await client.delete("/session/nonexistent-id/end")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_versions_empty(client):
    resp = await client.post("/session/create")
    session_id = resp.json()["session_id"]

    resp = await client.get(f"/session/{session_id}/versions")
    assert resp.status_code == 200
    assert resp.json()["versions"] == []


@pytest.mark.asyncio
async def test_get_versions_with_data(client, session_with_versions):
    session_id, versions = session_with_versions
    resp = await client.get(f"/session/{session_id}/versions")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["versions"]) == 2
    assert data["versions"][0]["version_index"] == 0
    assert data["versions"][1]["version_index"] == 1


# ── CPM analysis ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_analyze_version(client, session_with_versions):
    session_id, _ = session_with_versions
    resp = await client.post(f"/session/{session_id}/analyze", json={"version_index": 0})
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_index"] == 0
    assert data["has_cycles"] is False
    assert isinstance(data["critical_path"], list)
    assert data["project_duration_days"] > 0
    assert isinstance(data["task_floats"], dict)


@pytest.mark.asyncio
async def test_analyze_version_not_found(client):
    resp = await client.post("/session/create")
    session_id = resp.json()["session_id"]
    resp = await client.post(f"/session/{session_id}/analyze", json={"version_index": 99})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_analyze_caches_result(client, session_with_versions):
    session_id, _ = session_with_versions
    # First call
    await client.post(f"/session/{session_id}/analyze", json={"version_index": 0})
    # Cache should be populated
    cached = session_manager.cache_get(session_id, "cpm_0")
    assert cached is not None


# ── Diff endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diff_versions(client, session_with_versions):
    session_id, _ = session_with_versions
    resp = await client.post(
        f"/session/{session_id}/diff",
        json={"base_index": 0, "compare_index": 1},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["base_version_index"] == 0
    assert data["compare_version_index"] == 1
    assert "task_changes" in data
    assert "link_changes" in data


@pytest.mark.asyncio
async def test_diff_missing_version(client):
    resp = await client.post("/session/create")
    session_id = resp.json()["session_id"]
    v0 = simple_linear_schedule(version_index=0)
    session_manager.add_version(session_id, v0)
    resp = await client.post(
        f"/session/{session_id}/diff",
        json={"base_index": 0, "compare_index": 99},
    )
    assert resp.status_code == 404


# ── DCMA endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dcma_version(client, session_with_versions):
    session_id, _ = session_with_versions
    resp = await client.get(f"/session/{session_id}/dcma/0")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_index"] == 0
    assert "overall_status" in data
    assert isinstance(data["metrics"], list)
    assert len(data["metrics"]) == 14


@pytest.mark.asyncio
async def test_dcma_not_found(client):
    resp = await client.post("/session/create")
    session_id = resp.json()["session_id"]
    resp = await client.get(f"/session/{session_id}/dcma/0")
    assert resp.status_code == 404


# ── Forensics endpoint ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_forensics_endpoint(client):
    resp = await client.post("/session/create")
    session_id = resp.json()["session_id"]

    versions = forensics_multi_version()
    for v in versions:
        session_manager.add_version(session_id, v)

    resp = await client.post(
        f"/session/{session_id}/forensics",
        json={"version_indices": [0, 1, 2]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_indices"] == [0, 1, 2]
    assert data["manipulation_risk_score"] > 0.0
    assert len(data["findings"]) > 0


@pytest.mark.asyncio
async def test_forensics_no_matching_versions(client):
    resp = await client.post("/session/create")
    session_id = resp.json()["session_id"]
    resp = await client.post(
        f"/session/{session_id}/forensics",
        json={"version_indices": [99]},
    )
    assert resp.status_code == 400


# ── Chat endpoint ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chat_valid_critical_path(client, session_with_versions):
    session_id, _ = session_with_versions
    resp = await client.post(
        f"/session/{session_id}/chat",
        json={"query": "Does the project have a valid critical path?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "valid_critical_path"
    assert "response_text" in data


@pytest.mark.asyncio
async def test_chat_missing_logic(client, session_with_versions):
    session_id, _ = session_with_versions
    resp = await client.post(
        f"/session/{session_id}/chat",
        json={"query": "Which tasks have missing logic?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "missing_logic"


@pytest.mark.asyncio
async def test_chat_fallback(client, session_with_versions):
    session_id, _ = session_with_versions
    resp = await client.post(
        f"/session/{session_id}/chat",
        json={"query": "What is the meaning of life?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "fallback"
    assert "supported_intents" in data["data"]


@pytest.mark.asyncio
async def test_chat_float_risks(client, session_with_versions):
    session_id, _ = session_with_versions
    # First run CPM so the cache is warm
    await client.post(f"/session/{session_id}/analyze", json={"version_index": 1})
    resp = await client.post(
        f"/session/{session_id}/chat",
        json={"query": "What are the top float risks?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["intent"] == "float_risks"


# ── Health check ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "jvm_available" in data


# ── 404 for unknown session ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_session_returns_404(client):
    fake_id = "00000000-0000-0000-0000-000000000000"
    resp = await client.get(f"/session/{fake_id}/versions")
    assert resp.status_code == 404

    resp = await client.post(f"/session/{fake_id}/analyze", json={"version_index": 0})
    assert resp.status_code == 404

    resp = await client.get(f"/session/{fake_id}/dcma/0")
    assert resp.status_code == 404

    resp = await client.post(f"/session/{fake_id}/diff", json={"base_index": 0, "compare_index": 1})
    assert resp.status_code == 404

    resp = await client.post(f"/session/{fake_id}/forensics", json={"version_indices": [0]})
    assert resp.status_code == 404

    resp = await client.post(f"/session/{fake_id}/chat", json={"query": "test"})
    assert resp.status_code == 404
