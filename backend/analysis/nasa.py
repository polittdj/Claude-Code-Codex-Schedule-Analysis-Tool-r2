"""NASA Schedule Management Handbook compliance checks."""

from __future__ import annotations

import logging
from typing import Optional

from backend.models.schemas import (
    CPMResult,
    NASACheck,
    NASAResult,
    ScheduleVersion,
)

logger = logging.getLogger(__name__)


def check_nasa_compliance(
    version: ScheduleVersion,
    cpm_result: Optional[CPMResult] = None,
) -> NASAResult:
    """Run NASA Schedule Management Handbook compliance checks.

    Returns:
        NASAResult with all checks populated.
    """
    checks: list[NASACheck] = []

    checks.append(_check_all_work_authorized(version))
    checks.append(_check_logic_network_complete(version))
    checks.append(_check_hard_constraints_justified(version))
    checks.append(_check_critical_path_identifiable(version, cpm_result))
    checks.append(_check_reasonable_durations(version))
    checks.append(_check_resources_assigned(version))
    checks.append(_check_baseline_exists(version))
    checks.append(_check_no_negative_float(version, cpm_result))
    checks.append(_check_schedule_margin(version, cpm_result))

    overall_passed = all(c.passed for c in checks)

    return NASAResult(
        version_index=version.version_index,
        checks=checks,
        overall_passed=overall_passed,
    )


def _check_all_work_authorized(version: ScheduleVersion) -> NASACheck:
    """All tasks should have at least a WBS code or name indicating authorized work."""
    orphan_tasks = [
        t for t in version.tasks
        if not t.is_summary and not t.is_loe and not t.wbs and not t.name
    ]
    passed = len(orphan_tasks) == 0
    return NASACheck(
        check_id="nasa_01",
        name="All authorized work included (no unnamed/WBS-less tasks)",
        passed=passed,
        details=f"Found {len(orphan_tasks)} tasks with no name or WBS" if not passed else "All tasks have names",
        affected_task_ids=[t.unique_id for t in orphan_tasks],
    )


def _check_logic_network_complete(version: ScheduleVersion) -> NASACheck:
    """No open ends except project start/finish milestones."""
    task_ids = {t.unique_id for t in version.tasks if not t.is_summary and not t.is_loe}
    pred_set = {lnk.succ_unique_id for lnk in version.links}
    succ_set = {lnk.pred_unique_id for lnk in version.links}

    # Start milestones: no predecessors (expected)
    # End milestones: no successors (expected)
    # Problem: non-milestone tasks with no predecessors OR no successors
    open_end_tasks = []
    for t in version.tasks:
        if t.is_summary or t.is_loe:
            continue
        no_pred = t.unique_id not in pred_set
        no_succ = t.unique_id not in succ_set
        if (no_pred or no_succ) and not (t.is_milestone and (no_pred or no_succ)):
            if no_pred and no_succ:
                open_end_tasks.append(t.unique_id)  # complete orphan

    passed = len(open_end_tasks) == 0
    return NASACheck(
        check_id="nasa_02",
        name="Logic network complete (no orphan tasks)",
        passed=passed,
        details=f"Found {len(open_end_tasks)} orphan tasks" if not passed else "No orphan tasks",
        affected_task_ids=open_end_tasks,
    )


def _check_hard_constraints_justified(version: ScheduleVersion) -> NASACheck:
    """Hard constraints should be minimal and justified (flag if > 5% of active tasks)."""
    active = [t for t in version.tasks if not t.is_summary and not t.is_loe and t.percent_complete < 100]
    hard_ct = {"MSO", "MFO", "SNET", "SNLT"}
    hard_constrained = [t for t in active if t.constraint_type in hard_ct]
    ratio = len(hard_constrained) / max(len(active), 1)
    passed = ratio <= 0.05

    return NASACheck(
        check_id="nasa_03",
        name="Hard constraints justified (≤5% of active tasks)",
        passed=passed,
        details=f"{len(hard_constrained)}/{len(active)} tasks ({ratio:.1%}) have hard constraints",
        affected_task_ids=[t.unique_id for t in hard_constrained],
    )


def _check_critical_path_identifiable(
    version: ScheduleVersion,
    cpm_result: Optional[CPMResult],
) -> NASACheck:
    """Critical path must be identifiable and continuous."""
    if cpm_result is None:
        return NASACheck(
            check_id="nasa_04",
            name="Critical path identifiable",
            passed=False,
            details="No CPM data provided",
        )

    if cpm_result.has_cycles:
        return NASACheck(
            check_id="nasa_04",
            name="Critical path identifiable",
            passed=False,
            details="Schedule has logic loops/cycles",
            affected_task_ids=cpm_result.cycle_tasks,
        )

    has_cp = len(cpm_result.critical_path) > 0
    return NASACheck(
        check_id="nasa_04",
        name="Critical path identifiable",
        passed=has_cp,
        details=f"Critical path: {len(cpm_result.critical_path)} tasks" if has_cp else "No critical path found",
    )


def _check_reasonable_durations(version: ScheduleVersion) -> NASACheck:
    """Flag tasks with duration > 44 working days (NASA guideline)."""
    THRESHOLD = 44.0
    active = [
        t for t in version.tasks
        if not t.is_summary and not t.is_loe and not t.is_milestone
        and t.percent_complete < 100 and t.duration_days > THRESHOLD
    ]
    passed = len(active) == 0

    return NASACheck(
        check_id="nasa_05",
        name="Reasonable durations (≤44 days per task)",
        passed=passed,
        details=f"{len(active)} tasks exceed 44-day duration limit" if not passed else "All task durations within limit",
        affected_task_ids=[t.unique_id for t in active],
    )


def _check_resources_assigned(version: ScheduleVersion) -> NASACheck:
    """All non-milestone active tasks should have resources assigned."""
    active_nm = [
        t for t in version.tasks
        if not t.is_summary and not t.is_loe and not t.is_milestone
        and t.percent_complete < 100
    ]
    no_res = [t for t in active_nm if len(t.resources) == 0]
    passed = len(no_res) == 0

    return NASACheck(
        check_id="nasa_06",
        name="Resources assigned to all active tasks",
        passed=passed,
        details=f"{len(no_res)} tasks missing resource assignments" if not passed else "All tasks have resources",
        affected_task_ids=[t.unique_id for t in no_res],
    )


def _check_baseline_exists(version: ScheduleVersion) -> NASACheck:
    """At least some tasks should have baseline data."""
    tasks_with_baseline = [
        t for t in version.tasks
        if t.baseline_start or t.baseline_finish or t.baseline_duration_days
    ]
    passed = len(tasks_with_baseline) > 0

    return NASACheck(
        check_id="nasa_07",
        name="Baseline exists and is maintained",
        passed=passed,
        details=f"{len(tasks_with_baseline)} tasks have baseline data" if passed else "No baseline data found",
    )


def _check_no_negative_float(
    version: ScheduleVersion,
    cpm_result: Optional[CPMResult],
) -> NASACheck:
    """No task should have negative total float."""
    neg_float_tasks: list[str] = []
    if cpm_result:
        neg_float_tasks = [
            uid for uid, tf in cpm_result.task_floats.items()
            if tf.total_float < 0
        ]
    else:
        neg_float_tasks = [
            t.unique_id for t in version.tasks
            if t.total_float is not None and t.total_float < 0
        ]

    passed = len(neg_float_tasks) == 0
    return NASACheck(
        check_id="nasa_08",
        name="No negative total float",
        passed=passed,
        details=f"{len(neg_float_tasks)} tasks have negative float" if not passed else "No negative float",
        affected_task_ids=neg_float_tasks,
    )


def _check_schedule_margin(
    version: ScheduleVersion,
    cpm_result: Optional[CPMResult],
) -> NASACheck:
    """Schedule margin: project finish should have buffer after last activity."""
    if not cpm_result or not version.project_finish or not version.project_start:
        return NASACheck(
            check_id="nasa_09",
            name="Schedule margin (buffer at project end)",
            passed=True,
            details="Insufficient data to evaluate schedule margin",
        )

    project_days = (version.project_finish - version.project_start).days
    cp_duration = cpm_result.project_duration_days or project_days
    margin_days = project_days - cp_duration
    passed = margin_days >= 0

    return NASACheck(
        check_id="nasa_09",
        name="Schedule margin (buffer at project end)",
        passed=passed,
        details=f"Schedule margin: {margin_days:.1f} days",
    )
