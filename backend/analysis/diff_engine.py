"""Diff Engine — field-level comparison of schedule versions."""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.models.schemas import (
    Link,
    LinkChange,
    ScheduleVersion,
    Task,
    TaskChange,
    VersionDiff,
)

logger = logging.getLogger(__name__)

# Task fields to diff (order matters for display)
TASK_DIFF_FIELDS = [
    "name",
    "duration_days",
    "remaining_duration_days",
    "percent_complete",
    "actual_start",
    "actual_finish",
    "early_start",
    "early_finish",
    "late_start",
    "late_finish",
    "total_float",
    "free_float",
    "constraint_type",
    "constraint_date",
    "is_critical",
    "is_milestone",
    "is_summary",
    "is_loe",
    "wbs",
    "resources",
    "baseline_start",
    "baseline_finish",
    "baseline_duration_days",
]

LINK_DIFF_FIELDS = ["relationship_type", "lag_days"]


def diff_versions(
    base: ScheduleVersion,
    compare: ScheduleVersion,
    base_cpm: Optional[Any] = None,
    compare_cpm: Optional[Any] = None,
) -> VersionDiff:
    """Compute a VersionDiff between two ScheduleVersion objects.

    Args:
        base: The earlier/reference version.
        compare: The later/updated version.
        base_cpm: Optional CPMResult for base (enables float delta).
        compare_cpm: Optional CPMResult for compare.

    Returns:
        VersionDiff with task and link changes.
    """
    base_tasks = {t.unique_id: t for t in base.tasks}
    compare_tasks = {t.unique_id: t for t in compare.tasks}

    task_changes: list[TaskChange] = []

    all_task_ids = set(base_tasks) | set(compare_tasks)

    base_cpm_floats = base_cpm.task_floats if base_cpm else {}
    compare_cpm_floats = compare_cpm.task_floats if compare_cpm else {}

    for uid in sorted(all_task_ids):
        in_base = uid in base_tasks
        in_compare = uid in compare_tasks

        if in_base and not in_compare:
            task = base_tasks[uid]
            task_changes.append(
                TaskChange(
                    unique_id=uid,
                    name=task.name,
                    change_type="removed",
                    float_delta=None,
                    duration_delta=None,
                )
            )
        elif not in_base and in_compare:
            task = compare_tasks[uid]
            task_changes.append(
                TaskChange(
                    unique_id=uid,
                    name=task.name,
                    change_type="added",
                    float_delta=None,
                    duration_delta=None,
                )
            )
        else:
            # Both versions have this task — compare fields
            base_t = base_tasks[uid]
            cmp_t = compare_tasks[uid]
            field_changes = _diff_task_fields(base_t, cmp_t)

            if not field_changes:
                continue  # No change

            float_delta = None
            if uid in base_cpm_floats and uid in compare_cpm_floats:
                float_delta = round(
                    compare_cpm_floats[uid].total_float - base_cpm_floats[uid].total_float,
                    4,
                )

            duration_delta = None
            if "duration_days" in field_changes:
                old_dur, new_dur = field_changes["duration_days"]
                duration_delta = round(float(new_dur or 0) - float(old_dur or 0), 4)

            # Critical path change detection
            cp_change = None
            if uid in base_cpm_floats and uid in compare_cpm_floats:
                was_crit = base_cpm_floats[uid].is_critical
                now_crit = compare_cpm_floats[uid].is_critical
                if not was_crit and now_crit:
                    cp_change = "became_critical"
                elif was_crit and not now_crit:
                    cp_change = "left_critical"

            task_changes.append(
                TaskChange(
                    unique_id=uid,
                    name=cmp_t.name,
                    change_type="modified",
                    field_changes=field_changes,
                    float_delta=float_delta,
                    duration_delta=duration_delta,
                    critical_path_change=cp_change,
                )
            )

    # Diff links
    link_changes = _diff_links(base.links, compare.links)

    # Aggregate metrics
    new_critical = sum(
        1 for uid in compare_cpm_floats
        if compare_cpm_floats[uid].is_critical
        and uid in base_cpm_floats
        and not base_cpm_floats[uid].is_critical
    )
    removed_critical = sum(
        1 for uid in base_cpm_floats
        if base_cpm_floats[uid].is_critical
        and uid in compare_cpm_floats
        and not compare_cpm_floats[uid].is_critical
    )

    # Project finish delta
    proj_delta = None
    if base.project_finish and compare.project_finish:
        proj_delta = float((compare.project_finish - base.project_finish).days)
    elif base_cpm and compare_cpm and base_cpm.project_duration_days and compare_cpm.project_duration_days:
        proj_delta = round(
            compare_cpm.project_duration_days - base_cpm.project_duration_days, 4
        )

    cp_len_delta = None
    if base_cpm and compare_cpm:
        cp_len_delta = float(len(compare_cpm.critical_path) - len(base_cpm.critical_path))

    return VersionDiff(
        base_version_index=base.version_index,
        compare_version_index=compare.version_index,
        task_changes=task_changes,
        link_changes=link_changes,
        project_finish_delta_days=proj_delta,
        critical_path_length_delta=cp_len_delta,
        new_critical_task_count=new_critical,
        removed_critical_task_count=removed_critical,
        total_task_changes=len(task_changes),
    )


def _diff_task_fields(base: Task, compare: Task) -> dict[str, tuple[Any, Any]]:
    """Compare task fields and return {field: (old, new)} for changed fields."""
    changes: dict[str, tuple[Any, Any]] = {}
    base_dict = base.model_dump()
    compare_dict = compare.model_dump()

    for field in TASK_DIFF_FIELDS:
        old_val = base_dict.get(field)
        new_val = compare_dict.get(field)
        if old_val != new_val:
            changes[field] = (old_val, new_val)

    return changes


def _diff_links(
    base_links: list[Link],
    compare_links: list[Link],
) -> list[LinkChange]:
    """Compare link sets and return added/removed/modified changes."""
    base_map: dict[tuple[str, str], Link] = {
        (lnk.pred_unique_id, lnk.succ_unique_id): lnk for lnk in base_links
    }
    compare_map: dict[tuple[str, str], Link] = {
        (lnk.pred_unique_id, lnk.succ_unique_id): lnk for lnk in compare_links
    }

    changes: list[LinkChange] = []
    all_pairs = set(base_map) | set(compare_map)

    for pair in sorted(all_pairs):
        pred_id, succ_id = pair
        in_base = pair in base_map
        in_compare = pair in compare_map

        if in_base and not in_compare:
            changes.append(
                LinkChange(
                    pred_unique_id=pred_id,
                    succ_unique_id=succ_id,
                    change_type="removed",
                )
            )
        elif not in_base and in_compare:
            changes.append(
                LinkChange(
                    pred_unique_id=pred_id,
                    succ_unique_id=succ_id,
                    change_type="added",
                )
            )
        else:
            base_lnk = base_map[pair]
            cmp_lnk = compare_map[pair]
            field_changes: dict[str, tuple[Any, Any]] = {}
            for field in LINK_DIFF_FIELDS:
                old_val = getattr(base_lnk, field)
                new_val = getattr(cmp_lnk, field)
                if old_val != new_val:
                    field_changes[field] = (old_val, new_val)

            if field_changes:
                changes.append(
                    LinkChange(
                        pred_unique_id=pred_id,
                        succ_unique_id=succ_id,
                        change_type="modified",
                        field_changes=field_changes,
                    )
                )

    return changes


def build_diff_matrix(
    versions: list[ScheduleVersion],
    cpm_results: Optional[dict[int, Any]] = None,
) -> list[VersionDiff]:
    """Build all pairwise diffs for a list of versions (upper triangle)."""
    diffs: list[VersionDiff] = []
    cpm_results = cpm_results or {}

    for i in range(len(versions)):
        for j in range(i + 1, len(versions)):
            base = versions[i]
            compare = versions[j]
            base_cpm = cpm_results.get(base.version_index)
            compare_cpm = cpm_results.get(compare.version_index)
            diffs.append(diff_versions(base, compare, base_cpm, compare_cpm))

    return diffs
