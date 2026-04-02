"""Rule-based intent router for the 'Ask the Schedule' chat panel.

No external LLM calls. All analysis is deterministic.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

SUPPORTED_INTENTS = [
    "What is driving [task ID / task name]?",
    "Why did [milestone name / task ID] slip?",
    "Show critical path for version [N]",
    "What changed between version [A] and version [B]?",
    "Flag manipulation risks for [task ID]",
    "What is the DCMA score for version [N]?",
    "What are the top float risks?",
    "Which tasks have missing logic?",
    "Does the project have a valid critical path?",
]

# ── Intent patterns ───────────────────────────────────────────────────────────

_PATTERNS = [
    (re.compile(r"what\s+is\s+driving\s+(.+)", re.IGNORECASE), "driving_path"),
    (re.compile(r"why\s+did\s+(.+?)\s+slip", re.IGNORECASE), "milestone_slip"),
    (re.compile(r"show\s+(?:me\s+)?(?:the\s+)?critical\s+path\s+(?:for\s+)?version\s+(\d+)", re.IGNORECASE), "critical_path"),
    (re.compile(r"what\s+changed\s+between\s+version\s+(\d+)\s+and\s+(?:version\s+)?(\d+)", re.IGNORECASE), "diff_summary"),
    (re.compile(r"flag\s+(?:manipulation\s+)?risk(?:s)?\s+(?:for\s+)?(.+)", re.IGNORECASE), "forensics_focal"),
    (re.compile(r"(?:what\s+is\s+the\s+)?dcma\s+(?:score\s+)?(?:for\s+)?version\s+(\d+)", re.IGNORECASE), "dcma_score"),
    (re.compile(r"top\s+float\s+risks?", re.IGNORECASE), "float_risks"),
    (re.compile(r"(?:which\s+tasks?\s+have\s+)?missing\s+logic", re.IGNORECASE), "missing_logic"),
    (re.compile(r"(?:does\s+(?:the\s+)?project\s+have\s+)?(?:a\s+)?valid\s+critical\s+path", re.IGNORECASE), "valid_critical_path"),
]


def route_query(
    query: str,
    versions: list[Any],
    cpm_results: Optional[dict[int, Any]] = None,
    diff_results: Optional[list[Any]] = None,
    dcma_results: Optional[dict[int, Any]] = None,
    forensics_result: Optional[Any] = None,
) -> dict[str, Any]:
    """Route a natural-language query to the appropriate analysis function.

    Returns:
        Dict with keys: intent, response_text, data (structured data for frontend).
    """
    query = query.strip()

    for pattern, intent in _PATTERNS:
        match = pattern.search(query)
        if match:
            return _dispatch(intent, match, versions, cpm_results, diff_results, dcma_results, forensics_result)

    return _fallback()


def _dispatch(
    intent: str,
    match: re.Match,
    versions: list[Any],
    cpm_results: Optional[dict[int, Any]],
    diff_results: Optional[list[Any]],
    dcma_results: Optional[dict[int, Any]],
    forensics_result: Optional[Any],
) -> dict[str, Any]:
    try:
        if intent == "driving_path":
            return _handle_driving_path(match.group(1), versions, cpm_results)
        elif intent == "milestone_slip":
            return _handle_milestone_slip(match.group(1), versions, diff_results)
        elif intent == "critical_path":
            return _handle_critical_path(int(match.group(1)), versions, cpm_results)
        elif intent == "diff_summary":
            return _handle_diff_summary(int(match.group(1)), int(match.group(2)), versions, diff_results)
        elif intent == "forensics_focal":
            return _handle_forensics_focal(match.group(1), forensics_result)
        elif intent == "dcma_score":
            return _handle_dcma_score(int(match.group(1)), dcma_results)
        elif intent == "float_risks":
            return _handle_float_risks(versions, cpm_results)
        elif intent == "missing_logic":
            return _handle_missing_logic(versions, dcma_results)
        elif intent == "valid_critical_path":
            return _handle_valid_critical_path(versions, cpm_results)
    except Exception as exc:
        logger.warning("Intent dispatch error for '%s': %s", intent, exc)
        return {"intent": intent, "response_text": f"Error processing query: {exc}", "data": {}}

    return _fallback()


def _handle_driving_path(
    task_ref: str,
    versions: list[Any],
    cpm_results: Optional[dict[int, Any]],
) -> dict[str, Any]:
    if not versions:
        return {"intent": "driving_path", "response_text": "No schedule versions loaded.", "data": {}}

    latest = versions[-1]
    task_map = {t.unique_id: t for t in latest.tasks}
    task_ref_clean = task_ref.strip().strip('"\'')

    # Find task by UID or name
    target = task_map.get(task_ref_clean)
    if target is None:
        # Try by name (case-insensitive)
        target = next(
            (t for t in latest.tasks if t.name.lower() == task_ref_clean.lower()),
            None,
        )

    if target is None:
        return {
            "intent": "driving_path",
            "response_text": f"Task '{task_ref_clean}' not found in latest version.",
            "data": {},
        }

    try:
        from backend.analysis.driving_path import trace_driving_path
        dp = trace_driving_path(latest, target.unique_id)
        path_names = [
            task_map.get(uid, type("T", (), {"name": uid})()).name
            if uid in task_map else uid
            for uid in dp.driving_path
        ]
        response = (
            f"Driving path to '{target.name}' (v{latest.version_index}):\n"
            + " → ".join(path_names)
        )
        return {"intent": "driving_path", "response_text": response, "data": dp.model_dump()}
    except Exception as exc:
        return {"intent": "driving_path", "response_text": f"Could not trace driving path: {exc}", "data": {}}


def _handle_milestone_slip(
    milestone_ref: str,
    versions: list[Any],
    diff_results: Optional[list[Any]],
) -> dict[str, Any]:
    if len(versions) < 2:
        return {"intent": "milestone_slip", "response_text": "Need at least 2 versions to detect slip.", "data": {}}

    milestone_ref_clean = milestone_ref.strip().strip('"\'')

    # Find the first version where the milestone finish date changed
    slip_events = []
    for i in range(len(versions) - 1):
        v_base = versions[i]
        v_cmp = versions[i + 1]
        base_tasks = {t.unique_id: t for t in v_base.tasks}
        cmp_tasks = {t.unique_id: t for t in v_cmp.tasks}

        # Find milestone by UID or name in both
        for uid in set(base_tasks) & set(cmp_tasks):
            t_base = base_tasks[uid]
            t_cmp = cmp_tasks[uid]
            if not t_cmp.is_milestone:
                continue
            if (t_cmp.unique_id == milestone_ref_clean or
                    t_cmp.name.lower() == milestone_ref_clean.lower()):
                if t_base.early_finish != t_cmp.early_finish:
                    slip_events.append({
                        "base_idx": v_base.version_index,
                        "cmp_idx": v_cmp.version_index,
                        "before": str(t_base.early_finish),
                        "after": str(t_cmp.early_finish),
                        "task_name": t_cmp.name,
                    })

    if not slip_events:
        response = f"No slip detected for '{milestone_ref_clean}' across loaded versions."
    else:
        first = slip_events[0]
        response = (
            f"'{first['task_name']}' first slipped between v{first['base_idx']} and "
            f"v{first['cmp_idx']}: {first['before']} → {first['after']}. "
            f"({len(slip_events)} slip event(s) total)"
        )

    return {"intent": "milestone_slip", "response_text": response, "data": {"slip_events": slip_events}}


def _handle_critical_path(
    version_idx: int,
    versions: list[Any],
    cpm_results: Optional[dict[int, Any]],
) -> dict[str, Any]:
    cpm = cpm_results.get(version_idx) if cpm_results else None
    version = next((v for v in versions if v.version_index == version_idx), None)

    if cpm is None:
        if version is None:
            return {"intent": "critical_path", "response_text": f"Version {version_idx} not found.", "data": {}}
        from backend.analysis.cpm import run_cpm
        cpm = run_cpm(version)

    if cpm.has_cycles:
        return {"intent": "critical_path", "response_text": f"Version {version_idx} has logic cycles.", "data": {}}

    task_map = {}
    if version:
        task_map = {t.unique_id: t for t in version.tasks}

    cp_names = [task_map[uid].name if uid in task_map else uid for uid in cpm.critical_path]
    response = (
        f"Critical path for v{version_idx} ({len(cpm.critical_path)} tasks, "
        f"duration={cpm.project_duration_days:.1f}d):\n"
        + " → ".join(cp_names[:20])
        + (" ..." if len(cp_names) > 20 else "")
    )

    return {
        "intent": "critical_path",
        "response_text": response,
        "data": {
            "version_index": version_idx,
            "critical_path": cpm.critical_path,
            "project_duration_days": cpm.project_duration_days,
        },
    }


def _handle_diff_summary(
    base_idx: int,
    compare_idx: int,
    versions: list[Any],
    diff_results: Optional[list[Any]],
) -> dict[str, Any]:
    diff = None
    if diff_results:
        diff = next(
            (d for d in diff_results if d.base_version_index == base_idx and d.compare_version_index == compare_idx),
            None,
        )

    if diff is None:
        # Compute on the fly
        base_v = next((v for v in versions if v.version_index == base_idx), None)
        cmp_v = next((v for v in versions if v.version_index == compare_idx), None)
        if base_v is None or cmp_v is None:
            return {"intent": "diff_summary", "response_text": f"Version {base_idx} or {compare_idx} not found.", "data": {}}
        from backend.analysis.diff_engine import diff_versions
        diff = diff_versions(base_v, cmp_v)

    added = sum(1 for c in diff.task_changes if c.change_type == "added")
    removed = sum(1 for c in diff.task_changes if c.change_type == "removed")
    modified = sum(1 for c in diff.task_changes if c.change_type == "modified")
    link_changes = len(diff.link_changes)

    response = (
        f"Changes v{base_idx}→v{compare_idx}: "
        f"{added} tasks added, {removed} removed, {modified} modified, "
        f"{link_changes} link changes."
    )
    if diff.project_finish_delta_days:
        delta_sign = "+" if diff.project_finish_delta_days >= 0 else ""
        response += f" Project finish: {delta_sign}{diff.project_finish_delta_days:.0f} days."

    return {"intent": "diff_summary", "response_text": response, "data": diff.model_dump()}


def _handle_forensics_focal(
    task_ref: str,
    forensics_result: Optional[Any],
) -> dict[str, Any]:
    task_ref_clean = task_ref.strip().strip('"\'')

    if forensics_result is None:
        return {"intent": "forensics_focal", "response_text": "No forensic analysis available. Run forensics first.", "data": {}}

    relevant = [
        f for f in forensics_result.findings
        if task_ref_clean in f.affected_task_ids
    ]

    if not relevant:
        response = f"No manipulation findings for task '{task_ref_clean}'."
    else:
        response = (
            f"Found {len(relevant)} manipulation risk(s) for '{task_ref_clean}':\n"
            + "\n".join(
                f"  [{f.severity}] {f.pattern} (confidence={f.confidence:.0%}): {f.evidence[:100]}..."
                for f in relevant
            )
        )

    return {
        "intent": "forensics_focal",
        "response_text": response,
        "data": {"findings": [f.model_dump() for f in relevant]},
    }


def _handle_dcma_score(
    version_idx: int,
    dcma_results: Optional[dict[int, Any]],
) -> dict[str, Any]:
    if dcma_results is None or version_idx not in dcma_results:
        return {"intent": "dcma_score", "response_text": f"No DCMA data for version {version_idx}. Run DCMA analysis first.", "data": {}}

    result = dcma_results[version_idx]
    warn_count = sum(1 for m in result.metrics if m.status == "warn")
    fail_count = sum(1 for m in result.metrics if m.status == "fail")
    response = (
        f"DCMA 14-Point Score for v{version_idx}: "
        f"Overall={result.overall_status.upper()}, "
        f"{fail_count} fail, {warn_count} warn, "
        f"{14 - fail_count - warn_count} pass."
    )

    return {"intent": "dcma_score", "response_text": response, "data": result.model_dump()}


def _handle_float_risks(
    versions: list[Any],
    cpm_results: Optional[dict[int, Any]],
) -> dict[str, Any]:
    if not versions or not cpm_results:
        return {"intent": "float_risks", "response_text": "No CPM data available.", "data": {}}

    latest_v = versions[-1]
    cpm = cpm_results.get(latest_v.version_index)
    if cpm is None:
        return {"intent": "float_risks", "response_text": "No CPM data for latest version.", "data": {}}

    task_map = {t.unique_id: t for t in latest_v.tasks}
    floats = sorted(
        [(uid, tf.total_float) for uid, tf in cpm.task_floats.items() if not tf.is_critical],
        key=lambda x: x[1],
    )[:10]

    if not floats:
        response = "No float risk data available."
    else:
        lines = [
            f"  {task_map[uid].name if uid in task_map else uid}: TF={tf:.1f}d"
            for uid, tf in floats
        ]
        response = f"Top float risks (lowest TF, v{latest_v.version_index}):\n" + "\n".join(lines)

    return {"intent": "float_risks", "response_text": response, "data": {"float_risks": floats}}


def _handle_missing_logic(
    versions: list[Any],
    dcma_results: Optional[dict[int, Any]],
) -> dict[str, Any]:
    if not versions:
        return {"intent": "missing_logic", "response_text": "No versions loaded.", "data": {}}

    latest_v = versions[-1]

    if dcma_results and latest_v.version_index in dcma_results:
        dcma = dcma_results[latest_v.version_index]
        m1 = next((m for m in dcma.metrics if m.metric_id == 1), None)
        if m1:
            task_map = {t.unique_id: t for t in latest_v.tasks}
            names = [task_map[uid].name if uid in task_map else uid for uid in m1.affected_task_ids[:10]]
            response = (
                f"Missing logic (v{latest_v.version_index}): {m1.count} task(s) — "
                + ", ".join(names)
                if names else "None."
            )
            return {"intent": "missing_logic", "response_text": response, "data": {"affected": m1.affected_task_ids}}

    # Compute on the fly
    from backend.analysis.dcma import compute_dcma
    dcma = compute_dcma(latest_v)
    m1 = next((m for m in dcma.metrics if m.metric_id == 1), None)
    task_map = {t.unique_id: t for t in latest_v.tasks}
    names = [task_map[uid].name if uid in task_map else uid for uid in (m1.affected_task_ids[:10] if m1 else [])]
    response = f"Missing logic: {m1.count if m1 else 0} task(s) — " + (", ".join(names) if names else "None.")
    return {"intent": "missing_logic", "response_text": response, "data": {"affected": m1.affected_task_ids if m1 else []}}


def _handle_valid_critical_path(
    versions: list[Any],
    cpm_results: Optional[dict[int, Any]],
) -> dict[str, Any]:
    if not versions:
        return {"intent": "valid_critical_path", "response_text": "No versions loaded.", "data": {}}

    latest_v = versions[-1]
    cpm = cpm_results.get(latest_v.version_index) if cpm_results else None

    if cpm is None:
        from backend.analysis.cpm import run_cpm
        cpm = run_cpm(latest_v)

    if cpm.has_cycles:
        response = f"NO — v{latest_v.version_index} has logic cycles (no valid critical path)."
        valid = False
    elif cpm.critical_path:
        response = f"YES — v{latest_v.version_index} has a valid critical path ({len(cpm.critical_path)} tasks)."
        valid = True
    else:
        response = f"UNCERTAIN — v{latest_v.version_index} CPM ran but no critical path identified."
        valid = False

    return {
        "intent": "valid_critical_path",
        "response_text": response,
        "data": {"valid": valid, "has_cycles": cpm.has_cycles, "cp_length": len(cpm.critical_path)},
    }


def _fallback() -> dict[str, Any]:
    return {
        "intent": "fallback",
        "response_text": (
            "I didn't understand that query. Supported questions:\n"
            + "\n".join(f"  • {q}" for q in SUPPORTED_INTENTS)
        ),
        "data": {"supported_intents": SUPPORTED_INTENTS},
    }
