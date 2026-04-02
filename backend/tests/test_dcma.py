"""Tests for DCMA 14-point metrics and NASA compliance checks."""

from __future__ import annotations

import pytest

from backend.analysis.cpm import run_cpm
from backend.analysis.dcma import compute_dcma
from backend.analysis.nasa import check_nasa_compliance
from backend.tests.synthetic.schedule_factory import (
    dcma_violations_schedule,
    parallel_path_schedule,
    simple_linear_schedule,
)


class TestDCMAViolations:
    """Test with the pre-planted violations schedule."""

    def setup_method(self):
        self.version = dcma_violations_schedule()
        self.cpm = run_cpm(self.version)
        self.result = compute_dcma(self.version, cpm_result=self.cpm)

    def test_result_has_14_metrics(self):
        assert len(self.result.metrics) == 14

    def test_metric_ids_sequential(self):
        ids = [m.metric_id for m in self.result.metrics]
        assert ids == list(range(1, 15))

    def test_missing_logic_detected(self):
        m1 = next(m for m in self.result.metrics if m.metric_id == 1)
        # Task 10 has no predecessors AND no successors
        assert m1.count >= 1
        assert "10" in m1.affected_task_ids
        assert m1.status in ("warn", "fail")

    def test_leads_detected(self):
        m2 = next(m for m in self.result.metrics if m.metric_id == 2)
        # Link 1→2 has lag=-2 (lead)
        assert m2.count >= 1
        assert m2.status in ("warn", "fail")

    def test_lags_detected(self):
        m3 = next(m for m in self.result.metrics if m.metric_id == 3)
        # Link 3→4 has lag=5
        assert m3.count >= 1
        assert m3.status in ("warn", "fail")

    def test_hard_constraints_detected(self):
        m5 = next(m for m in self.result.metrics if m.metric_id == 5)
        # Task 5 has MSO constraint
        assert m5.count >= 1
        assert "5" in m5.affected_task_ids

    def test_high_duration_detected(self):
        m8 = next(m for m in self.result.metrics if m.metric_id == 8)
        # Task 8 has duration=50 (> 44 threshold)
        assert m8.count >= 1
        assert "8" in m8.affected_task_ids

    def test_missing_resources_detected(self):
        m10 = next(m for m in self.result.metrics if m.metric_id == 10)
        # Task 9 has no resources
        assert m10.count >= 1
        assert "9" in m10.affected_task_ids

    def test_overall_status_reflects_failures(self):
        assert self.result.overall_status in ("warn", "fail")


class TestDCMACleanSchedule:
    """Test DCMA on simple linear schedule (should mostly pass)."""

    def setup_method(self):
        self.version = simple_linear_schedule()
        self.cpm = run_cpm(self.version)
        self.result = compute_dcma(self.version, cpm_result=self.cpm)

    def test_no_missing_logic(self):
        m1 = next(m for m in self.result.metrics if m.metric_id == 1)
        assert m1.count == 0

    def test_no_leads(self):
        m2 = next(m for m in self.result.metrics if m.metric_id == 2)
        assert m2.count == 0

    def test_no_lags(self):
        m3 = next(m for m in self.result.metrics if m.metric_id == 3)
        assert m3.count == 0

    def test_no_hard_constraints(self):
        m5 = next(m for m in self.result.metrics if m.metric_id == 5)
        assert m5.count == 0

    def test_no_negative_float(self):
        m7 = next(m for m in self.result.metrics if m.metric_id == 7)
        assert m7.count == 0

    def test_critical_path_test_passes(self):
        m12 = next(m for m in self.result.metrics if m.metric_id == 12)
        assert m12.status == "pass"


class TestDCMAWithNoCPM:
    """Test DCMA without CPM data — should still compute structural metrics."""

    def test_computes_without_cpm(self):
        version = dcma_violations_schedule()
        result = compute_dcma(version)  # no cpm_result
        assert len(result.metrics) == 14

    def test_missing_logic_still_detected_without_cpm(self):
        version = dcma_violations_schedule()
        result = compute_dcma(version)
        m1 = next(m for m in result.metrics if m.metric_id == 1)
        assert m1.count >= 1


class TestDCMADenominators:
    """Test that summary/LOE/completed tasks are excluded from denominators."""

    def test_summary_tasks_excluded(self):
        from backend.models.schemas import ScheduleVersion
        from backend.tests.synthetic.schedule_factory import make_link, make_task
        from datetime import date

        start = date(2025, 1, 6)
        tasks = [
            make_task("1", "Summary", duration_days=10, is_summary=True),
            make_task("2", "Task A", duration_days=5),
            make_task("3", "Task B", duration_days=5),
        ]
        links = [make_link("2", "3")]
        version = ScheduleVersion(
            version_index=0, filename="test.mpp", project_start=start,
            tasks=tasks, links=links,
        )
        result = compute_dcma(version)
        m1 = next(m for m in result.metrics if m.metric_id == 1)
        # Denominator should be 2 (not 3 — summary excluded)
        assert m1.denominator == 2

    def test_completed_tasks_excluded(self):
        from backend.models.schemas import ScheduleVersion
        from backend.tests.synthetic.schedule_factory import make_link, make_task
        from datetime import date

        start = date(2025, 1, 6)
        tasks = [
            make_task("1", "Completed Task", duration_days=5, percent_complete=100.0),
            make_task("2", "Active Task A", duration_days=5),
            make_task("3", "Active Task B", duration_days=5),
        ]
        links = [make_link("2", "3")]
        version = ScheduleVersion(
            version_index=0, filename="test.mpp", project_start=start,
            tasks=tasks, links=links,
        )
        result = compute_dcma(version)
        m1 = next(m for m in result.metrics if m.metric_id == 1)
        # Denominator should be 2 (completed task excluded)
        assert m1.denominator == 2


class TestNASACompliance:
    def test_simple_linear_mostly_passes(self):
        version = simple_linear_schedule()
        cpm = run_cpm(version)
        result = check_nasa_compliance(version, cpm_result=cpm)
        assert result.version_index == 0
        assert len(result.checks) > 0

    def test_critical_path_check_passes_with_cpm(self):
        version = simple_linear_schedule()
        cpm = run_cpm(version)
        result = check_nasa_compliance(version, cpm_result=cpm)
        cp_check = next(c for c in result.checks if c.check_id == "nasa_04")
        assert cp_check.passed is True

    def test_critical_path_check_fails_without_cpm(self):
        version = simple_linear_schedule()
        result = check_nasa_compliance(version, cpm_result=None)
        cp_check = next(c for c in result.checks if c.check_id == "nasa_04")
        assert cp_check.passed is False

    def test_baseline_check_fails_without_baseline(self):
        version = simple_linear_schedule()
        result = check_nasa_compliance(version)
        baseline_check = next(c for c in result.checks if c.check_id == "nasa_07")
        # simple_linear_schedule has no baseline data
        assert baseline_check.passed is False

    def test_hard_constraints_check_violations(self):
        version = dcma_violations_schedule()
        result = check_nasa_compliance(version)
        hc_check = next(c for c in result.checks if c.check_id == "nasa_03")
        assert hc_check.passed is False

    def test_resources_check_fails_when_missing(self):
        version = dcma_violations_schedule()
        result = check_nasa_compliance(version)
        res_check = next(c for c in result.checks if c.check_id == "nasa_06")
        assert res_check.passed is False

    def test_logic_network_orphan_detected(self):
        version = dcma_violations_schedule()
        result = check_nasa_compliance(version)
        logic_check = next(c for c in result.checks if c.check_id == "nasa_02")
        # Task 10 is an orphan
        assert logic_check.passed is False

    def test_overall_passed_reflects_checks(self):
        version = dcma_violations_schedule()
        result = check_nasa_compliance(version)
        # With violations, overall should be False
        assert result.overall_passed is False
