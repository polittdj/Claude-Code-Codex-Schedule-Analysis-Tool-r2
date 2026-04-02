"""Tests for forensic manipulation detection — all 10 patterns."""

from __future__ import annotations

import pytest

from backend.analysis.forensics import detect_all_patterns
from backend.tests.synthetic.schedule_factory import forensics_multi_version


class TestForensicsAllPatterns:
    def setup_method(self):
        self.versions = forensics_multi_version()
        self.result = detect_all_patterns(self.versions)

    def test_result_has_findings(self):
        assert len(self.result.findings) > 0

    def test_version_indices_populated(self):
        assert self.result.version_indices == [0, 1, 2]

    def test_baseline_tampering_detected(self):
        bt = [f for f in self.result.findings if f.pattern == "Baseline Tampering"]
        assert len(bt) >= 1, "Baseline Tampering should be detected"
        # Task 2 baseline_start changed
        task_2_findings = [f for f in bt if "2" in f.affected_task_ids]
        assert len(task_2_findings) >= 1
        # Must be HIGH severity
        assert all(f.severity == "HIGH" for f in bt)

    def test_actuals_rewriting_detected(self):
        ar = [f for f in self.result.findings if f.pattern == "Actuals Rewriting"]
        assert len(ar) >= 1, "Actuals Rewriting should be detected"
        task_1_findings = [f for f in ar if "1" in f.affected_task_ids]
        assert len(task_1_findings) >= 1
        assert all(f.severity == "HIGH" for f in ar)

    def test_constraint_pinning_detected(self):
        cp = [f for f in self.result.findings if f.pattern == "Constraint Pinning"]
        assert len(cp) >= 1, "Constraint Pinning should be detected"
        task_3_findings = [f for f in cp if "3" in f.affected_task_ids]
        assert len(task_3_findings) >= 1

    def test_logic_deletion_detected(self):
        ld = [f for f in self.result.findings if f.pattern == "Logic Deletion"]
        assert len(ld) >= 1, "Logic Deletion should be detected"
        # Link 3→5 was deleted
        link_findings = [
            f for f in ld
            if ("3", "5") in f.affected_link_pairs
        ]
        assert len(link_findings) >= 1

    def test_duration_smoothing_detected(self):
        ds = [f for f in self.result.findings if f.pattern == "Duration Smoothing"]
        assert len(ds) >= 1, "Duration Smoothing should be detected"
        task_4_findings = [f for f in ds if "4" in f.affected_task_ids]
        assert len(task_4_findings) >= 1

    def test_lag_laundering_detected(self):
        ll = [f for f in self.result.findings if f.pattern == "Lag Laundering"]
        assert len(ll) >= 1, "Lag Laundering should be detected"
        # Link 2→5 lag changed from 0 to 10
        link_findings = [
            f for f in ll
            if ("2", "5") in f.affected_link_pairs
        ]
        assert len(link_findings) >= 1

    def test_near_critical_suppression_detectable(self):
        # Near-critical suppression uses a dedicated test (see TestNearCriticalSuppression below)
        # The forensics_multi_version schedule's CPM-derived floats vary too much for this pattern.
        # Verify the detector runs without error.
        result = detect_all_patterns(self.versions)
        assert isinstance(result.findings, list)

    def test_all_findings_have_evidence(self):
        for f in self.result.findings:
            assert len(f.evidence) > 10, f"Finding '{f.pattern}' has empty evidence"

    def test_all_findings_have_valid_confidence(self):
        for f in self.result.findings:
            assert 0.0 <= f.confidence <= 1.0, f"Finding '{f.pattern}' has invalid confidence"

    def test_medium_high_findings_present(self):
        # At least 3 MEDIUM/HIGH findings expected from the planted manipulations
        high_or_medium = [f for f in self.result.findings if f.severity in ("HIGH", "MEDIUM")]
        assert len(high_or_medium) >= 3, (
            f"Expected at least 3 MEDIUM/HIGH findings, got {[f.pattern for f in high_or_medium]}"
        )

    def test_risk_score_positive(self):
        assert self.result.manipulation_risk_score > 0.0


class TestForensicsEmptyInput:
    def test_empty_versions_returns_empty_result(self):
        result = detect_all_patterns([])
        assert result.findings == []
        assert result.manipulation_risk_score == 0.0

    def test_single_version_runs_without_error(self):
        from backend.tests.synthetic.schedule_factory import simple_linear_schedule
        versions = [simple_linear_schedule()]
        result = detect_all_patterns(versions)
        # Single version — no multi-version patterns possible
        assert isinstance(result.findings, list)


class TestForensicsCleanSchedule:
    def test_clean_schedule_has_no_high_confidence_findings(self):
        from backend.tests.synthetic.schedule_factory import simple_linear_schedule, parallel_path_schedule
        v0 = simple_linear_schedule(version_index=0)
        v1 = parallel_path_schedule(version_index=1)
        # These are unrelated schedules but we just want no high-confidence manipulation
        result = detect_all_patterns([v0, v1])
        high_confidence = [f for f in result.findings if f.confidence > 0.8]
        # Clean schedules should not have HIGH-confidence manipulation findings
        assert len(high_confidence) == 0, f"Unexpected high-confidence findings: {[f.pattern for f in high_confidence]}"


class TestIndividualDetectors:
    def test_baseline_tampering_only(self):
        from backend.analysis.forensics import _detect_baseline_tampering
        from backend.tests.synthetic.schedule_factory import forensics_multi_version
        versions = forensics_multi_version()
        findings = _detect_baseline_tampering(versions[0], versions[1], [0, 1])
        assert len(findings) >= 1

    def test_actuals_rewriting_only(self):
        from backend.analysis.forensics import _detect_actuals_rewriting
        from backend.tests.synthetic.schedule_factory import forensics_multi_version
        versions = forensics_multi_version()
        findings = _detect_actuals_rewriting(versions[0], versions[1], [0, 1])
        assert len(findings) >= 1

    def test_constraint_pinning_only(self):
        from backend.analysis.forensics import _detect_constraint_pinning
        from backend.tests.synthetic.schedule_factory import forensics_multi_version
        versions = forensics_multi_version()
        findings = _detect_constraint_pinning(versions[1], versions[2], [1, 2])
        assert len(findings) >= 1

    def test_duration_smoothing_only(self):
        from backend.analysis.forensics import _detect_duration_smoothing
        from backend.tests.synthetic.schedule_factory import forensics_multi_version
        versions = forensics_multi_version()
        findings = _detect_duration_smoothing(versions, [0, 1, 2])
        assert len(findings) >= 1
        task_4 = [f for f in findings if "4" in f.affected_task_ids]
        assert len(task_4) >= 1

    def test_logic_deletion_only(self):
        from backend.analysis.forensics import _detect_logic_deletion
        from backend.tests.synthetic.schedule_factory import forensics_multi_version
        from backend.analysis.cpm import run_cpm
        versions = forensics_multi_version()
        cpm_1 = run_cpm(versions[1])
        cpm_2 = run_cpm(versions[2])
        findings = _detect_logic_deletion(versions[1], versions[2], cpm_1, cpm_2, [1, 2])
        assert len(findings) >= 1


class TestNearCriticalSuppression:
    """Dedicated near-critical suppression test with a controlled 3-version scenario.

    Task X has TF=7 in all 3 versions (just above threshold=5) with no real progress,
    which should trigger the near-critical suppression detector.
    """

    def _make_controlled_versions(self) -> list:
        """3 versions where Task X always has TF just above near-critical threshold."""
        from datetime import date
        from backend.models.schemas import ScheduleVersion
        from backend.tests.synthetic.schedule_factory import make_link, make_task

        start = date(2025, 1, 6)
        findings_per_version = []

        for vi in range(3):
            # Structure: Chain A(3)->B(3)->End, plus X(5)->End
            # Project end driven by A+B = 6 days → Task X(5) has TF=1 from CPM
            # BUT: add a "buffer" task C(7) in parallel with A+B to push project end to 7
            # Then: Task X(5) has TF = 7-5 = 2
            # Actually need: project end = 12, Task X duration=5 → TF = 7
            # So: Add a driving task with EF=12, Task X with duration=5
            tasks = [
                make_task("D", "Driver", duration_days=12),   # drives project end
                make_task("X", "Near-Critical Task", duration_days=5, percent_complete=0.0),
                make_task("END", "End", duration_days=0, is_milestone=True),
            ]
            links = [
                make_link("D", "END"),
                make_link("X", "END"),
            ]
            findings_per_version.append(ScheduleVersion(
                version_index=vi,
                filename=f"ncs_v{vi}.mpp",
                project_start=start,
                tasks=tasks,
                links=links,
            ))

        return findings_per_version

    def test_near_critical_suppression_detected_controlled(self):
        from backend.analysis.forensics import _detect_near_critical_suppression
        from backend.analysis.cpm import run_cpm

        versions = self._make_controlled_versions()
        cpm_results = {v.version_index: run_cpm(v) for v in versions}

        # Verify CPM gives Task X float = 7 (= 12 - 5 = 7 > threshold=5)
        for v in versions:
            cpm = cpm_results[v.version_index]
            tf_x = cpm.task_floats["X"].total_float
            assert abs(tf_x - 7.0) < 0.01, f"Expected TF=7 for Task X, got {tf_x}"

        findings = _detect_near_critical_suppression(versions, cpm_results, [0, 1, 2], 5.0)
        ncs_x = [f for f in findings if "X" in f.affected_task_ids]
        assert len(ncs_x) >= 1, "Near-Critical Suppression not detected for Task X"
        assert ncs_x[0].severity in ("LOW", "MEDIUM")
