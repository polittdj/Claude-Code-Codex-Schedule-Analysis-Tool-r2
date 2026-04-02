"""Synthetic schedule data factory for tests.

Builds ScheduleVersion objects in pure Python — no .mpp files, no Java required.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from backend.models.schemas import (
    Baseline,
    Link,
    ScheduleVersion,
    Task,
)


def make_task(
    uid: str,
    name: str,
    duration_days: float = 5.0,
    percent_complete: float = 0.0,
    is_milestone: bool = False,
    is_summary: bool = False,
    is_loe: bool = False,
    is_critical: bool = False,
    total_float: Optional[float] = None,
    free_float: Optional[float] = None,
    constraint_type: str = "ASAP",
    constraint_date: Optional[date] = None,
    actual_start: Optional[date] = None,
    actual_finish: Optional[date] = None,
    early_start: Optional[date] = None,
    early_finish: Optional[date] = None,
    late_start: Optional[date] = None,
    late_finish: Optional[date] = None,
    resources: Optional[list[str]] = None,
    baseline_start: Optional[date] = None,
    baseline_finish: Optional[date] = None,
    baseline_duration_days: Optional[float] = None,
    wbs: str = "",
) -> Task:
    return Task(
        unique_id=uid,
        name=name,
        duration_days=duration_days,
        remaining_duration_days=duration_days * (1.0 - percent_complete / 100.0),
        percent_complete=percent_complete,
        is_milestone=is_milestone,
        is_summary=is_summary,
        is_loe=is_loe,
        is_critical=is_critical,
        total_float=total_float,
        free_float=free_float,
        constraint_type=constraint_type,
        constraint_date=constraint_date,
        actual_start=actual_start,
        actual_finish=actual_finish,
        early_start=early_start,
        early_finish=early_finish,
        late_start=late_start,
        late_finish=late_finish,
        resources=resources or [],
        baseline_start=baseline_start,
        baseline_finish=baseline_finish,
        baseline_duration_days=baseline_duration_days,
        wbs=wbs,
    )


def make_link(
    pred: str,
    succ: str,
    rel: str = "FS",
    lag: float = 0.0,
) -> Link:
    return Link(
        pred_unique_id=pred,
        succ_unique_id=succ,
        relationship_type=rel,
        lag_days=lag,
    )


def make_baseline(
    uid: str,
    start: Optional[date] = None,
    finish: Optional[date] = None,
    duration_days: Optional[float] = None,
) -> Baseline:
    return Baseline(
        task_unique_id=uid,
        baseline_start=start,
        baseline_finish=finish,
        baseline_duration_days=duration_days,
    )


# ── Pre-built schedules ───────────────────────────────────────────────────────


def simple_linear_schedule(version_index: int = 0) -> ScheduleVersion:
    """A → B → C → D (milestone). A simple 4-task FS chain.

    Hand-calculated CPM:
      A: ES=0, EF=5,  TF=0
      B: ES=5, EF=10, TF=0
      C: ES=10, EF=15, TF=0
      D: ES=15, EF=15, TF=0 (milestone, duration=0)
    All on critical path.
    """
    start = date(2025, 1, 6)
    tasks = [
        make_task("1", "Task A", duration_days=5, early_start=start,
                  early_finish=start + timedelta(days=5), wbs="1"),
        make_task("2", "Task B", duration_days=5, wbs="2"),
        make_task("3", "Task C", duration_days=5, wbs="3"),
        make_task("4", "Milestone D", duration_days=0, is_milestone=True, wbs="4"),
    ]
    links = [
        make_link("1", "2"),
        make_link("2", "3"),
        make_link("3", "4"),
    ]
    return ScheduleVersion(
        version_index=version_index,
        filename=f"simple_v{version_index}.mpp",
        status_date=start,
        project_start=start,
        project_finish=start + timedelta(days=15),
        tasks=tasks,
        links=links,
    )


def parallel_path_schedule(version_index: int = 0) -> ScheduleVersion:
    """Two parallel paths converging at a milestone.

    Path 1: A(5) → B(10) → End
    Path 2: C(3) → D(3)  → End

    Expected:
      Path 1 total = 15 days (critical)
      Path 2 total = 6 days  (float = 9)
    """
    start = date(2025, 1, 6)
    tasks = [
        make_task("1", "Task A", duration_days=5),
        make_task("2", "Task B", duration_days=10),
        make_task("3", "Task C", duration_days=3),
        make_task("4", "Task D", duration_days=3),
        make_task("5", "End Milestone", duration_days=0, is_milestone=True),
    ]
    links = [
        make_link("1", "2"),
        make_link("2", "5"),
        make_link("3", "4"),
        make_link("4", "5"),
    ]
    return ScheduleVersion(
        version_index=version_index,
        filename=f"parallel_v{version_index}.mpp",
        status_date=start,
        project_start=start,
        project_finish=start + timedelta(days=15),
        tasks=tasks,
        links=links,
    )


def dcma_violations_schedule(version_index: int = 0) -> ScheduleVersion:
    """Schedule with known DCMA violations planted:

    - Task 10: no predecessors, no successors (missing logic)
    - Link 1→2: lag = -2 days (lead)
    - Link 3→4: lag = 5 days (positive lag)
    - Task 5: constraint MSO (hard constraint)
    - Task 6: TF will be set to 50 (high float)
    - Task 7: TF will be set to -2 (negative float)
    - Task 8: duration = 50 days (high duration)
    - Task 9: no resources
    """
    start = date(2025, 1, 6)
    status = date(2025, 3, 1)
    tasks = [
        make_task("1", "Task 1 - Start", duration_days=5, resources=["Alice"]),
        make_task("2", "Task 2", duration_days=5, resources=["Bob"]),
        make_task("3", "Task 3", duration_days=5, resources=["Carol"]),
        make_task("4", "Task 4", duration_days=5, resources=["Dave"]),
        make_task(
            "5",
            "Task 5 - Hard Constraint",
            duration_days=5,
            constraint_type="MSO",
            constraint_date=date(2025, 2, 1),
            resources=["Eve"],
        ),
        make_task("6", "Task 6 - High Float", duration_days=5, total_float=50.0,
                  resources=["Frank"]),
        make_task("7", "Task 7 - Negative Float", duration_days=5, total_float=-2.0,
                  resources=["Grace"]),
        make_task("8", "Task 8 - Long Duration", duration_days=50, resources=["Hank"]),
        make_task("9", "Task 9 - No Resources", duration_days=5, resources=[]),
        make_task("10", "Task 10 - Orphan (no logic)", duration_days=5, resources=["Iris"]),
        make_task("11", "End Milestone", duration_days=0, is_milestone=True),
    ]
    links = [
        make_link("1", "2", lag=-2.0),   # lead
        make_link("2", "11"),
        make_link("3", "4", lag=5.0),    # lag
        make_link("4", "11"),
        make_link("5", "11"),
        make_link("6", "11"),
        make_link("7", "11"),
        make_link("8", "11"),
        make_link("9", "11"),
        # Task 10 intentionally has no links
    ]
    return ScheduleVersion(
        version_index=version_index,
        filename=f"dcma_v{version_index}.mpp",
        status_date=status,
        project_start=start,
        project_finish=start + timedelta(days=60),
        tasks=tasks,
        links=links,
    )


def multi_version_pair() -> tuple[ScheduleVersion, ScheduleVersion]:
    """Two versions for diffing tests.

    Version 0 (baseline):  A(5) → B(5) → C(5) → End
    Version 1 (updated):
      - Task B duration changed from 5 to 8
      - Task D added (new)
      - Link A→B type unchanged but lag added = 2 days
      - Task C removed
    """
    start = date(2025, 1, 6)

    v0_tasks = [
        make_task("1", "Task A", duration_days=5, resources=["Alice"],
                  baseline_start=date(2025, 1, 6), baseline_finish=date(2025, 1, 11),
                  baseline_duration_days=5),
        make_task("2", "Task B", duration_days=5, resources=["Bob"],
                  baseline_start=date(2025, 1, 11), baseline_finish=date(2025, 1, 18),
                  baseline_duration_days=5),
        make_task("3", "Task C", duration_days=5, resources=["Carol"]),
        make_task("99", "End", duration_days=0, is_milestone=True),
    ]
    v0_links = [
        make_link("1", "2"),
        make_link("2", "3"),
        make_link("3", "99"),
    ]
    v0 = ScheduleVersion(
        version_index=0,
        filename="schedule_v0.mpp",
        status_date=start,
        project_start=start,
        project_finish=start + timedelta(days=15),
        tasks=v0_tasks,
        links=v0_links,
    )

    v1_tasks = [
        make_task("1", "Task A", duration_days=5, resources=["Alice"],
                  baseline_start=date(2025, 1, 6), baseline_finish=date(2025, 1, 11),
                  baseline_duration_days=5),
        make_task("2", "Task B", duration_days=8, resources=["Bob"],  # duration changed
                  baseline_start=date(2025, 1, 11), baseline_finish=date(2025, 1, 18),
                  baseline_duration_days=5),
        # Task 3 (C) removed
        make_task("4", "Task D", duration_days=3, resources=["Dave"]),  # new task
        make_task("99", "End", duration_days=0, is_milestone=True),
    ]
    v1_links = [
        make_link("1", "2", lag=2.0),  # lag added
        make_link("2", "4"),
        make_link("4", "99"),
    ]
    v1 = ScheduleVersion(
        version_index=1,
        filename="schedule_v1.mpp",
        status_date=start + timedelta(days=30),
        project_start=start,
        project_finish=start + timedelta(days=20),
        tasks=v1_tasks,
        links=v1_links,
    )

    return v0, v1


def forensics_multi_version() -> list[ScheduleVersion]:
    """Three versions with planted forensic manipulation patterns.

    Plants:
      v0→v1: Baseline Tampering (task 2 baseline_start changed)
      v0→v1: Actuals Rewriting (task 1 actual_finish changed after 100% complete)
      v1→v2: Constraint Pinning (task 3 changed from ASAP to MSO)
      v1→v2: Logic Deletion (link 3→5 removed; task 5 critical)
      v0→v1→v2: Duration Smoothing (task 4 reduces by 5 each version)
      v1→v2: Lag Laundering (link 2→5 lag changed 0→10)
      v0→v1→v2: Near-Critical Suppression (task 6 float stays at 6 across all versions)
    """
    start = date(2025, 1, 6)

    def _make_version(
        idx: int,
        t2_bsl_start: date,
        t1_actual_finish: Optional[date],
        t3_constraint: str,
        t3_constraint_date: Optional[date],
        t4_duration: float,
        link_3_5_present: bool,
        link_2_5_lag: float,
        t6_float: float,
        status: date,
    ) -> ScheduleVersion:
        tasks = [
            make_task(
                "1", "Task 1 - Completed",
                duration_days=5, percent_complete=100.0,
                actual_start=start, actual_finish=t1_actual_finish,
                resources=["Alice"],
            ),
            make_task(
                "2", "Task 2",
                duration_days=5, resources=["Bob"],
                baseline_start=t2_bsl_start,
                baseline_finish=t2_bsl_start + timedelta(days=5),
                baseline_duration_days=5,
            ),
            make_task(
                "3", "Task 3",
                duration_days=5, resources=["Carol"],
                constraint_type=t3_constraint,
                constraint_date=t3_constraint_date,
            ),
            make_task("4", "Task 4 - Smoothed", duration_days=t4_duration, resources=["Dave"]),
            make_task("5", "End Milestone", duration_days=0, is_milestone=True, is_critical=True),
            make_task("6", "Task 6 - Near-Critical", duration_days=5,
                      total_float=t6_float, resources=["Eve"]),
        ]
        links = [
            make_link("1", "2"),
            make_link("2", "5", lag=link_2_5_lag),
            make_link("4", "5"),
            make_link("6", "5"),
        ]
        if link_3_5_present:
            links.append(make_link("3", "5"))

        return ScheduleVersion(
            version_index=idx,
            filename=f"forensics_v{idx}.mpp",
            status_date=status,
            project_start=start,
            project_finish=start + timedelta(days=30),
            tasks=tasks,
            links=links,
        )

    v0 = _make_version(
        0,
        t2_bsl_start=date(2025, 1, 13),
        t1_actual_finish=date(2025, 1, 11),
        t3_constraint="ASAP",
        t3_constraint_date=None,
        t4_duration=15.0,
        link_3_5_present=True,
        link_2_5_lag=0.0,
        t6_float=6.0,
        status=date(2025, 1, 31),
    )
    v1 = _make_version(
        1,
        t2_bsl_start=date(2025, 1, 20),  # Baseline Tampered (changed from Jan 13)
        t1_actual_finish=date(2025, 1, 15),  # Actuals Rewritten (was Jan 11)
        t3_constraint="ASAP",
        t3_constraint_date=None,
        t4_duration=10.0,  # Duration Smoothed -5
        link_3_5_present=True,
        link_2_5_lag=0.0,
        t6_float=6.0,  # Near-Critical still at 6
        status=date(2025, 2, 28),
    )
    v2 = _make_version(
        2,
        t2_bsl_start=date(2025, 1, 20),
        t1_actual_finish=date(2025, 1, 15),
        t3_constraint="MSO",  # Constraint Pinned
        t3_constraint_date=date(2025, 3, 1),
        t4_duration=5.0,  # Duration Smoothed -5 again
        link_3_5_present=False,  # Logic Deleted
        link_2_5_lag=10.0,  # Lag Laundered
        t6_float=6.0,  # Near-Critical still at 6
        status=date(2025, 3, 31),
    )

    return [v0, v1, v2]
