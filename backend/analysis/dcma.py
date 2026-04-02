"""DCMA 14-Point Schedule Health Metrics per DCMA-EA PAM 200.1 Section 4."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

import networkx as nx

from backend.models.schemas import (
    CPMResult,
    DCMAMetric,
    DCMAResult,
    ScheduleVersion,
    Task,
)

logger = logging.getLogger(__name__)

# DCMA thresholds (as ratios, 0–1)
THRESHOLD_WARN = 0.05
THRESHOLD_FAIL = 0.10
HIGH_FLOAT_DAYS = 44.0
HIGH_DURATION_DAYS = 44.0
LAG_THRESHOLD_DAYS = 0.0  # any positive lag


def compute_dcma(
    version: ScheduleVersion,
    cpm_result: Optional[CPMResult] = None,
    high_float_threshold: float = HIGH_FLOAT_DAYS,
    high_duration_threshold: float = HIGH_DURATION_DAYS,
    lag_threshold: float = LAG_THRESHOLD_DAYS,
) -> DCMAResult:
    """Compute all 14 DCMA metrics for a schedule version.

    Args:
        version: The schedule version to evaluate.
        cpm_result: Optional CPM result with float data.
        high_float_threshold: Days above which TF is considered "high float".
        high_duration_threshold: Days above which remaining duration is "high".
        lag_threshold: Lags strictly greater than this are counted.

    Returns:
        DCMAResult with all 14 metrics populated.
    """
    tasks = version.tasks
    links = version.links
    status_date = version.status_date

    # Denominator: active tasks (exclude completed, LOE, summary, milestones for most metrics)
    active = [
        t for t in tasks
        if not t.is_loe
        and not t.is_summary
        and t.percent_complete < 100.0
        and not t.is_milestone
    ]
    active_ids = {t.unique_id for t in active}

    # Non-milestone active
    nm_active = [t for t in active if not t.is_milestone]

    # Build predecessor/successor sets
    pred_set: set[str] = set()   # tasks that HAVE predecessors
    succ_set: set[str] = set()   # tasks that HAVE successors

    for lnk in links:
        succ_set.add(lnk.pred_unique_id)
        pred_set.add(lnk.succ_unique_id)

    task_floats = cpm_result.task_floats if cpm_result else {}

    metrics: list[DCMAMetric] = []

    # ── Metric 1: Missing Logic ───────────────────────────────────────────────
    missing_logic = [
        t for t in active
        if t.unique_id not in pred_set and t.unique_id not in succ_set
    ]
    metrics.append(_make_metric(
        1, "Missing Logic (no predecessors AND no successors)",
        count=len(missing_logic),
        denom=len(active),
        affected=[t.unique_id for t in missing_logic],
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 2: Leads (negative lag) ───────────────────────────────────────
    leads = [lnk for lnk in links if lnk.lag_days < 0]
    metrics.append(_make_metric(
        2, "Leads (negative lag)",
        count=len(leads),
        denom=max(len(links), 1),
        affected=[lnk.succ_unique_id for lnk in leads],
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 3: Lags (positive lag > threshold) ────────────────────────────
    lags = [lnk for lnk in links if lnk.lag_days > lag_threshold]
    metrics.append(_make_metric(
        3, f"Lags (positive lag > {lag_threshold} days)",
        count=len(lags),
        denom=max(len(links), 1),
        affected=[lnk.succ_unique_id for lnk in lags],
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 4: Non-FS Relationships ───────────────────────────────────────
    non_fs = [lnk for lnk in links if lnk.relationship_type != "FS"]
    metrics.append(_make_metric(
        4, "Non-FS Relationships",
        count=len(non_fs),
        denom=max(len(links), 1),
        affected=[lnk.succ_unique_id for lnk in non_fs],
        warn=0.10, fail=0.20,
        notes="DCMA expects predominantly FS relationships",
    ))

    # ── Metric 5: Hard Constraints ────────────────────────────────────────────
    hard_constraint_types = {"MSO", "MFO", "SNET", "SNLT"}
    hard_constrained = [
        t for t in active
        if t.constraint_type in hard_constraint_types
    ]
    metrics.append(_make_metric(
        5, "Hard Constraints (MSO/MFO/SNET/SNLT)",
        count=len(hard_constrained),
        denom=len(active),
        affected=[t.unique_id for t in hard_constrained],
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 6: High Float ─────────────────────────────────────────────────
    high_float = [
        t for t in active
        if task_floats.get(t.unique_id) is not None
        and task_floats[t.unique_id].total_float > high_float_threshold
    ]
    # Also check Task.total_float if CPM not provided
    if not task_floats:
        high_float = [
            t for t in active
            if t.total_float is not None and t.total_float > high_float_threshold
        ]
    metrics.append(_make_metric(
        6, f"High Float (TF > {high_float_threshold} days)",
        count=len(high_float),
        denom=len(active),
        affected=[t.unique_id for t in high_float],
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 7: Negative Float ─────────────────────────────────────────────
    neg_float = [
        t for t in active
        if task_floats.get(t.unique_id) is not None
        and task_floats[t.unique_id].total_float < 0
    ]
    if not task_floats:
        neg_float = [
            t for t in active
            if t.total_float is not None and t.total_float < 0
        ]
    metrics.append(_make_metric(
        7, "Negative Float (TF < 0)",
        count=len(neg_float),
        denom=len(active),
        affected=[t.unique_id for t in neg_float],
        warn=0.0, fail=THRESHOLD_WARN,
    ))

    # ── Metric 8: High Duration ───────────────────────────────────────────────
    high_dur = [
        t for t in nm_active
        if t.remaining_duration_days > high_duration_threshold
    ]
    metrics.append(_make_metric(
        8, f"High Duration (remaining > {high_duration_threshold} days)",
        count=len(high_dur),
        denom=len(nm_active),
        affected=[t.unique_id for t in high_dur],
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 9: Invalid Dates ───────────────────────────────────────────────
    invalid_dates: list[str] = []
    proj_start = version.project_start
    proj_finish = version.project_finish
    for t in tasks:
        if t.is_summary or t.is_loe or t.percent_complete >= 100:
            continue
        if t.early_start and t.early_finish and t.early_finish < t.early_start:
            invalid_dates.append(t.unique_id)
        if t.actual_start and t.actual_finish and t.actual_finish < t.actual_start:
            invalid_dates.append(t.unique_id)
        if proj_start and t.early_start and t.early_start < proj_start:
            invalid_dates.append(t.unique_id)
        if proj_finish and t.early_finish and t.early_finish > proj_finish:
            invalid_dates.append(t.unique_id)
    all_active_ids_for_dates = {t.unique_id for t in tasks if not t.is_summary}
    metrics.append(_make_metric(
        9, "Invalid Dates",
        count=len(set(invalid_dates)),
        denom=len(all_active_ids_for_dates),
        affected=list(set(invalid_dates)),
        warn=0.0, fail=THRESHOLD_WARN,
    ))

    # ── Metric 10: Missing Resources ─────────────────────────────────────────
    no_resources = [t for t in nm_active if len(t.resources) == 0]
    metrics.append(_make_metric(
        10, "Missing Resources",
        count=len(no_resources),
        denom=len(nm_active),
        affected=[t.unique_id for t in no_resources],
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 11: Missed Actuals ─────────────────────────────────────────────
    missed_actuals: list[str] = []
    if status_date:
        for t in nm_active:
            # Task that should have started by status date but has no actual start
            if t.early_start and t.early_start <= status_date and not t.actual_start:
                missed_actuals.append(t.unique_id)
            # Task with actual start but zero progress
            if t.actual_start and t.percent_complete == 0.0:
                missed_actuals.append(t.unique_id)
    metrics.append(_make_metric(
        11, "Missed Actuals",
        count=len(set(missed_actuals)),
        denom=len(nm_active),
        affected=list(set(missed_actuals)),
        warn=THRESHOLD_WARN, fail=THRESHOLD_FAIL,
    ))

    # ── Metric 12: Critical Path Test ─────────────────────────────────────────
    has_valid_cp = False
    cp_notes = "No CPM data provided"
    if cpm_result and cpm_result.critical_path:
        has_valid_cp = len(cpm_result.critical_path) > 0 and not cpm_result.has_cycles
        cp_notes = f"Critical path has {len(cpm_result.critical_path)} tasks"
    metrics.append(DCMAMetric(
        metric_id=12,
        name="Critical Path Test (single continuous path exists)",
        value=1.0 if has_valid_cp else 0.0,
        count=1 if has_valid_cp else 0,
        denominator=1,
        status="pass" if has_valid_cp else "warn",
        notes=cp_notes,
    ))

    # ── Metric 13: CPLI ───────────────────────────────────────────────────────
    cpli = None
    cpli_notes = "Requires baseline and CPM"
    if cpm_result and cpm_result.project_duration_days:
        # Simplified CPLI: if we have all TF data for critical tasks
        critical_tasks = [
            t for t in tasks
            if t.unique_id in task_floats and task_floats[t.unique_id].is_critical
        ]
        if critical_tasks:
            remaining_dur = sum(t.remaining_duration_days for t in critical_tasks)
            avg_tf = sum(
                task_floats[t.unique_id].total_float for t in critical_tasks
            ) / len(critical_tasks)
            if remaining_dur > 0:
                cpli = round((remaining_dur + avg_tf) / remaining_dur, 4)
                cpli_notes = f"CPLI={cpli:.4f}"

    cpli_status = "info"
    if cpli is not None:
        if cpli < 0.80:
            cpli_status = "fail"
        elif cpli < 0.95:
            cpli_status = "warn"
        else:
            cpli_status = "pass"

    metrics.append(DCMAMetric(
        metric_id=13,
        name="Critical Path Length Index (CPLI)",
        value=cpli,
        status=cpli_status,
        notes=cpli_notes,
    ))

    # ── Metric 14: BEI ────────────────────────────────────────────────────────
    bei = None
    bei_notes = "Requires status date"
    if status_date:
        scheduled_complete = [
            t for t in tasks
            if not t.is_summary and not t.is_loe
            and t.early_finish and t.early_finish <= status_date
        ]
        actually_complete = [
            t for t in scheduled_complete
            if t.percent_complete >= 100.0
        ]
        if scheduled_complete:
            bei = round(len(actually_complete) / len(scheduled_complete), 4)
            bei_notes = f"BEI={bei:.4f} ({len(actually_complete)}/{len(scheduled_complete)})"

    bei_status = "info"
    if bei is not None:
        if bei < 0.80:
            bei_status = "fail"
        elif bei < 0.95:
            bei_status = "warn"
        else:
            bei_status = "pass"

    metrics.append(DCMAMetric(
        metric_id=14,
        name="Baseline Execution Index (BEI)",
        value=bei,
        status=bei_status,
        notes=bei_notes,
    ))

    # Determine overall status
    statuses = [m.status for m in metrics]
    if "fail" in statuses:
        overall = "fail"
    elif "warn" in statuses:
        overall = "warn"
    else:
        overall = "pass"

    return DCMAResult(
        version_index=version.version_index,
        metrics=metrics,
        overall_status=overall,
    )


def _make_metric(
    metric_id: int,
    name: str,
    count: int,
    denom: int,
    affected: list[str],
    warn: float,
    fail: float,
    notes: str = "",
) -> DCMAMetric:
    value = round(count / denom, 4) if denom > 0 else 0.0
    if value >= fail:
        status = "fail"
    elif value >= warn:
        status = "warn"
    else:
        status = "pass"

    return DCMAMetric(
        metric_id=metric_id,
        name=name,
        value=value,
        count=count,
        denominator=denom,
        threshold_warn=warn,
        threshold_fail=fail,
        status=status,
        affected_task_ids=affected,
        notes=notes,
    )
