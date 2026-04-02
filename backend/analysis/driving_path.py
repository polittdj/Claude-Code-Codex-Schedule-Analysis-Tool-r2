"""Driving Path Tracer — identifies the chain of predecessors that is driving a focal task."""

from __future__ import annotations

import logging
from typing import Optional

import networkx as nx

from backend.analysis.cpm import FLOAT_EPSILON, _build_graph, _backward_pass, _forward_pass
from backend.models.schemas import DrivingPathLink, DrivingPathResult, ScheduleVersion
from datetime import date

logger = logging.getLogger(__name__)


def trace_driving_path(
    version: ScheduleVersion,
    target_task_id: str,
) -> DrivingPathResult:
    """Trace the driving predecessor chain for a focal task.

    A predecessor is 'driving' if removing it (or its relationship) would
    delay the focal task — equivalently, the free float on that link is zero.

    Args:
        version: The schedule version containing CPM results.
        target_task_id: The unique_id of the focal task.

    Returns:
        DrivingPathResult with ordered driving path and link details.
    """
    project_start = version.project_start or date.today()
    task_map = {t.unique_id: t for t in version.tasks}

    target_task = task_map.get(target_task_id)
    if target_task is None:
        return DrivingPathResult(
            target_task_id=target_task_id,
            target_task_name="[Task not found]",
            driving_path=[],
            driving_links=[],
        )

    G = _build_graph(version)
    if not nx.is_directed_acyclic_graph(G):
        return DrivingPathResult(
            target_task_id=target_task_id,
            target_task_name=target_task.name,
            driving_path=[target_task_id],
            driving_links=[],
        )

    _forward_pass(G, task_map, project_start)
    _backward_pass(G, task_map, project_start)

    # Walk backward from target using DFS, following only driving predecessors
    driving_path: list[str] = []
    driving_links: list[DrivingPathLink] = []
    visited: set[str] = set()

    def _walk_back(node: str) -> None:
        if node in visited or node == "__START__":
            return
        visited.add(node)

        driving_preds = []
        for pred, _, data in G.in_edges(node, data=True):
            if pred == "__START__":
                continue
            if _is_driving_link(G, pred, node, data):
                driving_preds.append((pred, data))

        for pred, data in driving_preds:
            pred_task = task_map.get(pred)
            succ_task = task_map.get(node)
            link_obj = DrivingPathLink(
                pred_unique_id=pred,
                succ_unique_id=node,
                relationship_type=data.get("rel_type", "FS"),
                lag_days=data.get("lag", 0.0),
                pred_name=pred_task.name if pred_task else pred,
                succ_name=succ_task.name if succ_task else node,
                is_driving=True,
            )
            driving_links.insert(0, link_obj)
            driving_path.insert(0, pred)
            _walk_back(pred)

    _walk_back(target_task_id)

    if target_task_id not in driving_path:
        driving_path.append(target_task_id)

    return DrivingPathResult(
        target_task_id=target_task_id,
        target_task_name=target_task.name,
        driving_path=driving_path,
        driving_links=driving_links,
        full_trace=_build_full_trace(G, task_map, driving_path),
    )


def _is_driving_link(
    G: nx.DiGraph,
    pred: str,
    succ: str,
    data: dict,
) -> bool:
    """Return True if the pred→succ link has zero free float on it."""
    rel = data.get("rel_type", "FS")
    lag = data.get("lag", 0.0)
    pred_ES = G.nodes[pred].get("ES", 0.0)
    pred_EF = G.nodes[pred].get("EF", 0.0)
    succ_ES = G.nodes[succ].get("ES", 0.0)
    succ_EF = G.nodes[succ].get("EF", 0.0)

    if rel == "FS":
        return abs(pred_EF + lag - succ_ES) < FLOAT_EPSILON
    elif rel == "SS":
        return abs(pred_ES + lag - succ_ES) < FLOAT_EPSILON
    elif rel == "FF":
        return abs(pred_EF + lag - succ_EF) < FLOAT_EPSILON
    elif rel == "SF":
        return abs(pred_ES + lag - succ_EF) < FLOAT_EPSILON
    return False


def _build_full_trace(
    G: nx.DiGraph,
    task_map: dict,
    path: list[str],
) -> list[dict]:
    """Build a rich trace dict for each task in the driving path."""
    trace = []
    for uid in path:
        task = task_map.get(uid)
        nd = G.nodes.get(uid, {})
        trace.append({
            "unique_id": uid,
            "name": task.name if task else uid,
            "duration_days": task.duration_days if task else 0,
            "ES": nd.get("ES"),
            "EF": nd.get("EF"),
            "LS": nd.get("LS"),
            "LF": nd.get("LF"),
            "TF": round(nd.get("LF", 0) - nd.get("EF", 0), 4),
        })
    return trace
