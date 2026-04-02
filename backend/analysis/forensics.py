"""Forensic Schedule Manipulation Detection — 10 patterns with evidence output."""

from __future__ import annotations

import logging
import statistics
from typing import Any, Optional

from backend.analysis.cpm import run_cpm
from backend.analysis.driving_path import trace_driving_path
from backend.models.schemas import (
    CPMResult,
    ForensicFinding,
    ForensicsResult,
    ScheduleVersion,
    Task,
)

logger = logging.getLogger(__name__)

NEAR_CRITICAL_THRESHOLD = 5.0
FLOAT_HARVEST_MIN_GAIN = 10.0    # days of float gain to flag
PROGRESS_INFLATION_THRESHOLD = 50.0  # pct_complete jump threshold


def detect_all_patterns(
    versions: list[ScheduleVersion],
    cpm_results: Optional[dict[int, CPMResult]] = None,
    near_critical_threshold: float = NEAR_CRITICAL_THRESHOLD,
) -> ForensicsResult:
    """Run all 10 forensic manipulation detectors across a set of versions.

    Args:
        versions: List of ScheduleVersion objects (at least 2 for multi-version patterns).
        cpm_results: Pre-computed CPM results keyed by version_index.
        near_critical_threshold: Float threshold for near-critical detection (days).

    Returns:
        ForensicsResult with all findings and an aggregate risk score.
    """
    if not versions:
        return ForensicsResult(version_indices=[], findings=[])

    # Compute CPM if not provided
    if cpm_results is None:
        cpm_results = {}
        for v in versions:
            try:
                cpm_results[v.version_index] = run_cpm(v, near_critical_threshold)
            except Exception as exc:
                logger.warning("CPM failed for version %d: %s", v.version_index, exc)

    findings: list[ForensicFinding] = []
    version_indices = [v.version_index for v in versions]

    # Single-version checks (applied to latest version)
    # (None — all our detectors are multi-version)

    # Multi-version checks require at least 2 versions
    for i in range(len(versions) - 1):
        base = versions[i]
        compare = versions[i + 1]
        base_cpm = cpm_results.get(base.version_index)
        compare_cpm = cpm_results.get(compare.version_index)
        pair_idxs = [base.version_index, compare.version_index]

        findings += _detect_baseline_tampering(base, compare, pair_idxs)
        findings += _detect_actuals_rewriting(base, compare, pair_idxs)
        findings += _detect_constraint_pinning(base, compare, pair_idxs)
        findings += _detect_logic_deletion(base, compare, base_cpm, compare_cpm, pair_idxs)
        findings += _detect_lag_laundering(base, compare, pair_idxs)
        findings += _detect_progress_inflation(base, compare, pair_idxs)

    # Patterns that require 3+ versions (trend-based)
    if len(versions) >= 3:
        all_ids = sorted(
            set(v.version_index for v in versions),
            key=lambda i: next(v.version_index for v in versions if v.version_index == i),
        )
        findings += _detect_duration_smoothing(versions, version_indices)
        findings += _detect_near_critical_suppression(versions, cpm_results, version_indices, near_critical_threshold)

    # Patterns that require 2+ versions for cross-version comparison
    if len(versions) >= 2:
        findings += _detect_float_harvesting(versions, cpm_results, near_critical_threshold, version_indices)
        findings += _detect_driving_path_swap(versions, cpm_results, version_indices)

    # Aggregate risk score: weighted by severity
    severity_weights = {"HIGH": 1.0, "MEDIUM": 0.5, "LOW": 0.2}
    if findings:
        total_weight = sum(severity_weights.get(f.severity, 0.5) * f.confidence for f in findings)
        max_possible = len(findings) * 1.0  # if everything were HIGH + confidence=1
        risk_score = min(total_weight / max(max_possible, 1.0), 1.0)
    else:
        risk_score = 0.0

    return ForensicsResult(
        version_indices=version_indices,
        findings=findings,
        manipulation_risk_score=round(risk_score, 4),
    )


# ── Pattern 1: Driving Path Swap ─────────────────────────────────────────────


def _detect_driving_path_swap(
    versions: list[ScheduleVersion],
    cpm_results: dict[int, CPMResult],
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    milestones_v0 = [t for t in versions[0].tasks if t.is_milestone]

    for milestone in milestones_v0:
        paths_by_version: dict[int, set[str]] = {}
        milestone_dates: dict[int, Any] = {}

        for v in versions:
            task_in_v = next((t for t in v.tasks if t.unique_id == milestone.unique_id), None)
            if task_in_v is None:
                continue
            milestone_dates[v.version_index] = task_in_v.early_finish
            try:
                dp = trace_driving_path(v, milestone.unique_id)
                paths_by_version[v.version_index] = set(dp.driving_path)
            except Exception:
                pass

        if len(paths_by_version) < 2:
            continue

        v_ids = sorted(paths_by_version.keys())
        for i in range(len(v_ids) - 1):
            v_a, v_b = v_ids[i], v_ids[i + 1]
            path_a = paths_by_version[v_a]
            path_b = paths_by_version[v_b]
            date_a = milestone_dates.get(v_a)
            date_b = milestone_dates.get(v_b)

            if path_a == path_b:
                continue

            # Path changed
            added_to_path = path_b - path_a
            removed_from_path = path_a - path_b

            # Suspicious if date stayed the same despite path change
            date_unchanged = date_a == date_b
            confidence = 0.6 if date_unchanged else 0.3

            if added_to_path or removed_from_path:
                findings.append(ForensicFinding(
                    pattern="Driving Path Swap",
                    severity="MEDIUM",
                    affected_task_ids=list(added_to_path | removed_from_path | {milestone.unique_id}),
                    evidence=(
                        f"Driving path to milestone '{milestone.name}' (UID={milestone.unique_id}) "
                        f"changed between v{v_a} and v{v_b}. "
                        f"Tasks removed from driving path: {sorted(removed_from_path)}. "
                        f"Tasks added: {sorted(added_to_path)}. "
                        f"Milestone date {'unchanged' if date_unchanged else 'changed'}: {date_a} → {date_b}."
                    ),
                    confidence=confidence,
                    version_indices=[v_a, v_b],
                ))

    return findings


# ── Pattern 2: Lag Laundering ─────────────────────────────────────────────────


def _detect_lag_laundering(
    base: ScheduleVersion,
    compare: ScheduleVersion,
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    base_links = {(lnk.pred_unique_id, lnk.succ_unique_id): lnk for lnk in base.links}
    compare_links = {(lnk.pred_unique_id, lnk.succ_unique_id): lnk for lnk in compare.links}
    compare_tasks = {t.unique_id: t for t in compare.tasks}
    base_tasks = {t.unique_id: t for t in base.tasks}

    for pair, base_lnk in base_links.items():
        if pair not in compare_links:
            continue
        cmp_lnk = compare_links[pair]

        # Lag increased from 0 (or very small) to a notable positive value
        lag_increased = cmp_lnk.lag_days > base_lnk.lag_days and base_lnk.lag_days <= 0
        if not lag_increased or cmp_lnk.lag_days < 1.0:
            continue

        # Check if predecessor task also had duration reduced
        pred_id = pair[0]
        succ_id = pair[1]
        base_pred = base_tasks.get(pred_id)
        cmp_pred = compare_tasks.get(pred_id)

        dur_reduced = (
            base_pred and cmp_pred
            and cmp_pred.duration_days < base_pred.duration_days
        )

        severity = "MEDIUM" if dur_reduced else "LOW"
        confidence = 0.7 if dur_reduced else 0.4

        findings.append(ForensicFinding(
            pattern="Lag Laundering",
            severity=severity,
            affected_task_ids=[pred_id, succ_id],
            affected_link_pairs=[pair],
            evidence=(
                f"Link {pair[0]}→{pair[1]} lag changed from {base_lnk.lag_days:.1f} to "
                f"{cmp_lnk.lag_days:.1f} days between v{version_indices[0]} and v{version_indices[1]}. "
                + (
                    f"Predecessor task '{base_pred.name}' duration also reduced from "
                    f"{base_pred.duration_days:.1f} to {cmp_pred.duration_days:.1f} days. "
                    if dur_reduced else ""
                )
                + "This may be inflating float on downstream tasks."
            ),
            confidence=confidence,
            version_indices=version_indices,
        ))

    return findings


# ── Pattern 3: Constraint Pinning ─────────────────────────────────────────────


def _detect_constraint_pinning(
    base: ScheduleVersion,
    compare: ScheduleVersion,
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    base_tasks = {t.unique_id: t for t in base.tasks}

    hard_constraints = {"MSO", "MFO", "SNET", "SNLT"}
    soft_constraints = {"ASAP", "ALAP"}

    for cmp_task in compare.tasks:
        base_task = base_tasks.get(cmp_task.unique_id)
        if base_task is None:
            continue
        if base_task.constraint_type in soft_constraints and cmp_task.constraint_type in hard_constraints:
            # Task went from soft to hard constraint
            coincides_with_status = (
                compare.status_date and cmp_task.constraint_date
                and abs((cmp_task.constraint_date - compare.status_date).days) <= 14
            )
            severity = "HIGH" if coincides_with_status else "MEDIUM"
            confidence = 0.8 if coincides_with_status else 0.5

            findings.append(ForensicFinding(
                pattern="Constraint Pinning",
                severity=severity,
                affected_task_ids=[cmp_task.unique_id],
                evidence=(
                    f"Task '{cmp_task.name}' (UID={cmp_task.unique_id}) constraint changed from "
                    f"{base_task.constraint_type} to {cmp_task.constraint_type} "
                    f"(date: {cmp_task.constraint_date}) "
                    f"between v{version_indices[0]} and v{version_indices[1]}. "
                    + (
                        f"Constraint date coincides with status date {compare.status_date}. "
                        if coincides_with_status else ""
                    )
                    + "Hard constraints can artificially lock dates."
                ),
                confidence=confidence,
                version_indices=version_indices,
            ))

    return findings


# ── Pattern 4: Duration Smoothing ────────────────────────────────────────────


def _detect_duration_smoothing(
    versions: list[ScheduleVersion],
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    if len(versions) < 3:
        return findings

    # Build duration history per task
    task_dur_history: dict[str, list[tuple[int, float]]] = {}
    for v in versions:
        for t in v.tasks:
            if t.is_milestone or t.is_summary or t.is_loe:
                continue
            if t.unique_id not in task_dur_history:
                task_dur_history[t.unique_id] = []
            task_dur_history[t.unique_id].append((v.version_index, t.duration_days))

    for uid, history in task_dur_history.items():
        if len(history) < 3:
            continue

        durs = [d for _, d in history]
        deltas = [durs[i] - durs[i + 1] for i in range(len(durs) - 1)]

        # All deltas should be positive (always decreasing) and uniform
        if all(d > 0 for d in deltas):
            mean_delta = statistics.mean(deltas)
            if mean_delta < 0.1:
                continue
            try:
                stdev = statistics.stdev(deltas)
            except statistics.StatisticsError:
                stdev = 0.0
            cv = stdev / mean_delta if mean_delta > 0 else 0.0  # coefficient of variation

            if cv < 0.05:  # Less than 5% variation — suspiciously uniform
                task_name = next(
                    (t.name for v in versions for t in v.tasks if t.unique_id == uid),
                    uid,
                )
                findings.append(ForensicFinding(
                    pattern="Duration Smoothing",
                    severity="MEDIUM",
                    affected_task_ids=[uid],
                    evidence=(
                        f"Task '{task_name}' (UID={uid}) duration decreased by exactly "
                        f"{mean_delta:.1f} days per period across {len(history)} versions "
                        f"(CoV={cv:.3f} < 0.05). Duration history: "
                        + ", ".join(f"v{vi}={d:.1f}" for vi, d in history)
                        + ". Uniform reductions without corresponding progress suggest manipulation."
                    ),
                    confidence=0.7,
                    version_indices=version_indices,
                ))

    return findings


# ── Pattern 5: Baseline Tampering ────────────────────────────────────────────


def _detect_baseline_tampering(
    base: ScheduleVersion,
    compare: ScheduleVersion,
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    base_tasks = {t.unique_id: t for t in base.tasks}

    for cmp_task in compare.tasks:
        base_task = base_tasks.get(cmp_task.unique_id)
        if base_task is None:
            continue

        tampered_fields = []
        if base_task.baseline_start != cmp_task.baseline_start:
            tampered_fields.append(
                f"baseline_start: {base_task.baseline_start} → {cmp_task.baseline_start}"
            )
        if base_task.baseline_finish != cmp_task.baseline_finish:
            tampered_fields.append(
                f"baseline_finish: {base_task.baseline_finish} → {cmp_task.baseline_finish}"
            )
        if base_task.baseline_duration_days != cmp_task.baseline_duration_days:
            tampered_fields.append(
                f"baseline_duration: {base_task.baseline_duration_days} → {cmp_task.baseline_duration_days}"
            )

        if tampered_fields:
            findings.append(ForensicFinding(
                pattern="Baseline Tampering",
                severity="HIGH",
                affected_task_ids=[cmp_task.unique_id],
                evidence=(
                    f"Task '{cmp_task.name}' (UID={cmp_task.unique_id}) baseline data changed "
                    f"between v{version_indices[0]} and v{version_indices[1]}. "
                    "Baselines should be frozen after approval. "
                    "Changes: " + "; ".join(tampered_fields)
                ),
                confidence=0.95,
                version_indices=version_indices,
            ))

    return findings


# ── Pattern 6: Actuals Rewriting ─────────────────────────────────────────────


def _detect_actuals_rewriting(
    base: ScheduleVersion,
    compare: ScheduleVersion,
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    base_tasks = {t.unique_id: t for t in base.tasks}

    for cmp_task in compare.tasks:
        base_task = base_tasks.get(cmp_task.unique_id)
        if base_task is None:
            continue

        # Flag if task was 100% complete in base but actuals changed
        if base_task.percent_complete < 100.0:
            continue

        rewrites = []
        if base_task.actual_start != cmp_task.actual_start:
            rewrites.append(f"actual_start: {base_task.actual_start} → {cmp_task.actual_start}")
        if base_task.actual_finish != cmp_task.actual_finish:
            rewrites.append(f"actual_finish: {base_task.actual_finish} → {cmp_task.actual_finish}")

        if rewrites:
            findings.append(ForensicFinding(
                pattern="Actuals Rewriting",
                severity="HIGH",
                affected_task_ids=[cmp_task.unique_id],
                evidence=(
                    f"Task '{cmp_task.name}' (UID={cmp_task.unique_id}) was 100% complete "
                    f"in v{version_indices[0]} but actual dates changed in v{version_indices[1]}. "
                    "Completed tasks should not have actuals retroactively modified. "
                    "Changes: " + "; ".join(rewrites)
                ),
                confidence=0.90,
                version_indices=version_indices,
            ))

    return findings


# ── Pattern 7: Progress Inflation ────────────────────────────────────────────


def _detect_progress_inflation(
    base: ScheduleVersion,
    compare: ScheduleVersion,
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    base_tasks = {t.unique_id: t for t in base.tasks}

    for cmp_task in compare.tasks:
        base_task = base_tasks.get(cmp_task.unique_id)
        if base_task is None:
            continue
        if cmp_task.is_milestone or cmp_task.is_summary or cmp_task.is_loe:
            continue
        if cmp_task.duration_days < 5.0:
            continue  # Short tasks can jump fast legitimately

        pct_jump = cmp_task.percent_complete - base_task.percent_complete
        if pct_jump <= PROGRESS_INFLATION_THRESHOLD:
            continue

        # Check if remaining duration math is consistent:
        # expected_rem = duration * (1 - pct_complete/100)
        expected_rem = cmp_task.duration_days * (1.0 - cmp_task.percent_complete / 100.0)
        rem_mismatch = abs(cmp_task.remaining_duration_days - expected_rem) > 1.0

        severity = "HIGH" if rem_mismatch else "MEDIUM"
        confidence = 0.8 if rem_mismatch else 0.5

        findings.append(ForensicFinding(
            pattern="Progress Inflation",
            severity=severity,
            affected_task_ids=[cmp_task.unique_id],
            evidence=(
                f"Task '{cmp_task.name}' (UID={cmp_task.unique_id}) percent complete jumped "
                f"{pct_jump:.0f}% in one period (v{version_indices[0]}: "
                f"{base_task.percent_complete:.0f}% → v{version_indices[1]}: "
                f"{cmp_task.percent_complete:.0f}%) on a {cmp_task.duration_days:.0f}-day task. "
                + (
                    f"Remaining duration ({cmp_task.remaining_duration_days:.1f}) does not match "
                    f"expected ({expected_rem:.1f}) based on % complete. "
                    if rem_mismatch else ""
                )
            ),
            confidence=confidence,
            version_indices=version_indices,
        ))

    return findings


# ── Pattern 8: Logic Deletion ─────────────────────────────────────────────────


def _detect_logic_deletion(
    base: ScheduleVersion,
    compare: ScheduleVersion,
    base_cpm: Optional[CPMResult],
    compare_cpm: Optional[CPMResult],
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    base_links = {(lnk.pred_unique_id, lnk.succ_unique_id) for lnk in base.links}
    compare_links = {(lnk.pred_unique_id, lnk.succ_unique_id) for lnk in compare.links}

    removed_links = base_links - compare_links

    compare_cpm_floats = compare_cpm.task_floats if compare_cpm else {}
    compare_critical = {uid for uid, tf in compare_cpm_floats.items() if tf.is_critical}

    base_tasks = {t.unique_id: t for t in base.tasks}
    compare_tasks = {t.unique_id: t for t in compare.tasks}

    for pred_id, succ_id in removed_links:
        # Was the successor on the critical path in the compare version?
        succ_critical = succ_id in compare_critical

        pred_task = base_tasks.get(pred_id) or compare_tasks.get(pred_id)
        succ_task = base_tasks.get(succ_id) or compare_tasks.get(succ_id)

        severity = "HIGH" if succ_critical else "MEDIUM"
        confidence = 0.75 if succ_critical else 0.45

        findings.append(ForensicFinding(
            pattern="Logic Deletion",
            severity=severity,
            affected_task_ids=[pred_id, succ_id],
            affected_link_pairs=[(pred_id, succ_id)],
            evidence=(
                f"Logic link from '{pred_task.name if pred_task else pred_id}' "
                f"(UID={pred_id}) to '{succ_task.name if succ_task else succ_id}' "
                f"(UID={succ_id}) was removed between v{version_indices[0]} and "
                f"v{version_indices[1]}. "
                + (
                    "Successor task is on the critical path. "
                    if succ_critical else ""
                )
                + "Logic deletions without a change order are a red flag."
            ),
            confidence=confidence,
            version_indices=version_indices,
        ))

    return findings


# ── Pattern 9: Float Harvesting ───────────────────────────────────────────────


def _detect_float_harvesting(
    versions: list[ScheduleVersion],
    cpm_results: dict[int, CPMResult],
    near_critical_threshold: float,
    version_indices: list[int],
) -> list[ForensicFinding]:
    findings = []
    if len(versions) < 2:
        return findings

    for i in range(len(versions) - 1):
        base_v = versions[i]
        cmp_v = versions[i + 1]
        base_cpm = cpm_results.get(base_v.version_index)
        cmp_cpm = cpm_results.get(cmp_v.version_index)

        if not base_cpm or not cmp_cpm:
            continue

        base_floats = base_cpm.task_floats
        cmp_floats = cmp_cpm.task_floats

        for uid in base_floats:
            if uid not in cmp_floats:
                continue
            base_tf = base_floats[uid].total_float
            cmp_tf = cmp_floats[uid].total_float

            # Was near-critical before, now has significantly more float
            was_near_critical = base_tf <= near_critical_threshold
            float_increase = cmp_tf - base_tf

            if not was_near_critical or float_increase < FLOAT_HARVEST_MIN_GAIN:
                continue

            # Check if the float increase is justified by logic or duration changes
            # (If we see a float gain without related changes, it's suspicious)
            base_task = next((t for t in base_v.tasks if t.unique_id == uid), None)
            cmp_task = next((t for t in cmp_v.tasks if t.unique_id == uid), None)

            dur_change = abs(
                (cmp_task.duration_days if cmp_task else 0)
                - (base_task.duration_days if base_task else 0)
            ) > 1.0

            if not dur_change:
                task_name = cmp_task.name if cmp_task else uid
                findings.append(ForensicFinding(
                    pattern="Float Harvesting",
                    severity="MEDIUM",
                    affected_task_ids=[uid],
                    evidence=(
                        f"Task '{task_name}' (UID={uid}) was near-critical "
                        f"(TF={base_tf:.1f}d ≤ {near_critical_threshold:.0f}d threshold) "
                        f"in v{base_v.version_index} but float increased to {cmp_tf:.1f}d "
                        f"(+{float_increase:.1f}d) in v{cmp_v.version_index} "
                        "without corresponding duration change. "
                        "May indicate predecessor lag additions or logic manipulation."
                    ),
                    confidence=0.55,
                    version_indices=[base_v.version_index, cmp_v.version_index],
                ))

    return findings


# ── Pattern 10: Near-Critical Suppression ───────────────────────────────────


def _detect_near_critical_suppression(
    versions: list[ScheduleVersion],
    cpm_results: dict[int, CPMResult],
    version_indices: list[int],
    near_critical_threshold: float,
) -> list[ForensicFinding]:
    findings = []
    if len(versions) < 3:
        return findings

    # Track per-task float across all versions
    task_float_history: dict[str, list[tuple[int, float]]] = {}
    for v in versions:
        cpm = cpm_results.get(v.version_index)
        if not cpm:
            continue
        for uid, tf_obj in cpm.task_floats.items():
            if uid not in task_float_history:
                task_float_history[uid] = []
            task_float_history[uid].append((v.version_index, tf_obj.total_float))

    for uid, history in task_float_history.items():
        if len(history) < 3:
            continue

        floats = [f for _, f in history]

        # Pattern: float stays in a narrow band just above the near-critical threshold
        above_threshold = [f > near_critical_threshold for f in floats]
        below_threshold = [f <= near_critical_threshold for f in floats]

        if not all(above_threshold):
            continue  # Task was actually critical at some point — legit

        # All float values are just above threshold (within 2x threshold)
        max_float = max(floats)
        if max_float > near_critical_threshold * 3:
            continue  # Far above threshold — not suspicious

        # Float band: max - min should be small relative to threshold
        float_range = max_float - min(floats)
        if float_range > near_critical_threshold:
            continue

        # Check if progress is stagnant (pct_complete barely moving)
        pct_history = []
        for v in versions:
            task = next((t for t in v.tasks if t.unique_id == uid), None)
            if task:
                pct_history.append(task.percent_complete)

        pct_progress = (max(pct_history) - min(pct_history)) if pct_history else 100.0
        stagnant = pct_progress < 10.0

        task_name = next(
            (t.name for v in versions for t in v.tasks if t.unique_id == uid),
            uid,
        )
        findings.append(ForensicFinding(
            pattern="Near-Critical Suppression",
            severity="MEDIUM" if stagnant else "LOW",
            affected_task_ids=[uid],
            evidence=(
                f"Task '{task_name}' (UID={uid}) float stays in band "
                f"[{min(floats):.1f}–{max(floats):.1f}d] just above near-critical threshold "
                f"({near_critical_threshold:.0f}d) across {len(history)} versions. "
                + (
                    f"Percent complete barely changed ({min(pct_history):.0f}%→{max(pct_history):.0f}%). "
                    if stagnant else ""
                )
                + "Float may be manipulated to keep task off near-critical reporting."
            ),
            confidence=0.60 if stagnant else 0.35,
            version_indices=version_indices,
        ))

    return findings
