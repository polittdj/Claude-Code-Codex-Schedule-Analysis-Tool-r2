"""Tests for CPM engine and driving path tracer."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.analysis.cpm import FLOAT_EPSILON, run_cpm
from backend.analysis.driving_path import trace_driving_path
from backend.models.schemas import ScheduleVersion
from backend.tests.synthetic.schedule_factory import (
    make_link,
    make_task,
    parallel_path_schedule,
    simple_linear_schedule,
)


class TestCPMSimpleLinear:
    def setup_method(self):
        self.version = simple_linear_schedule()
        self.result = run_cpm(self.version)

    def test_no_cycles(self):
        assert self.result.has_cycles is False

    def test_project_duration(self):
        assert self.result.project_duration_days == 15.0

    def test_all_tasks_critical(self):
        for uid in ("1", "2", "3", "4"):
            assert self.result.task_floats[uid].is_critical, f"Task {uid} should be critical"

    def test_all_tasks_zero_float(self):
        for uid in ("1", "2", "3", "4"):
            tf = self.result.task_floats[uid].total_float
            assert abs(tf) < FLOAT_EPSILON, f"Task {uid} TF={tf} should be 0"


class TestCPMParallelPaths:
    def setup_method(self):
        self.version = parallel_path_schedule()
        self.result = run_cpm(self.version)

    def test_no_cycles(self):
        assert self.result.has_cycles is False

    def test_project_duration(self):
        assert self.result.project_duration_days == 15.0

    def test_critical_path_is_path1(self):
        for uid in ("1", "2"):
            assert self.result.task_floats[uid].is_critical

    def test_path2_has_float(self):
        tf3 = self.result.task_floats["3"].total_float
        tf4 = self.result.task_floats["4"].total_float
        assert abs(tf3 - 9.0) < FLOAT_EPSILON, f"Task 3 TF={tf3}, expected 9"
        assert abs(tf4 - 9.0) < FLOAT_EPSILON, f"Task 4 TF={tf4}, expected 9"

    def test_milestone_critical(self):
        assert self.result.task_floats["5"].is_critical


class TestCPMWithLag:
    """A(5) --FS+2--> B(5): project_duration=12, both critical."""

    def setup_method(self):
        start = date(2025, 1, 6)
        tasks = [make_task("1", "A", duration_days=5), make_task("2", "B", duration_days=5)]
        links = [make_link("1", "2", rel="FS", lag=2.0)]
        self.version = ScheduleVersion(
            version_index=0, filename="test.mpp", project_start=start,
            tasks=tasks, links=links,
        )
        self.result = run_cpm(self.version)

    def test_project_duration(self):
        assert self.result.project_duration_days == 12.0

    def test_both_critical(self):
        for uid in ("1", "2"):
            assert self.result.task_floats[uid].is_critical


class TestCPMWithSS:
    """A(10) --SS+3--> B(5): project=10, A critical, B has float=2."""

    def setup_method(self):
        start = date(2025, 1, 6)
        tasks = [make_task("1", "A", duration_days=10), make_task("2", "B", duration_days=5)]
        links = [make_link("1", "2", rel="SS", lag=3.0)]
        self.version = ScheduleVersion(
            version_index=0, filename="test.mpp", project_start=start,
            tasks=tasks, links=links,
        )
        self.result = run_cpm(self.version)

    def test_project_duration(self):
        assert self.result.project_duration_days == 10.0

    def test_task_a_critical(self):
        assert self.result.task_floats["1"].is_critical

    def test_task_b_float(self):
        tf = self.result.task_floats["2"].total_float
        assert abs(tf - 2.0) < FLOAT_EPSILON, f"Task B TF={tf}, expected 2"


class TestCPMWithFF:
    """A(5) --FF+0--> B(8): project=8, B critical, A has float=3."""

    def setup_method(self):
        start = date(2025, 1, 6)
        tasks = [make_task("1", "A", duration_days=5), make_task("2", "B", duration_days=8)]
        links = [make_link("1", "2", rel="FF", lag=0.0)]
        self.version = ScheduleVersion(
            version_index=0, filename="test.mpp", project_start=start,
            tasks=tasks, links=links,
        )
        self.result = run_cpm(self.version)

    def test_project_duration(self):
        assert self.result.project_duration_days == 8.0

    def test_task_b_critical(self):
        assert self.result.task_floats["2"].is_critical

    def test_task_a_float(self):
        tf = self.result.task_floats["1"].total_float
        assert abs(tf - 3.0) < FLOAT_EPSILON, f"Task A TF={tf}, expected 3"


class TestCPMWithSNETConstraint:
    """A(5) --FS--> B(5) SNET=day8: project=13, A has float=8, B critical."""

    def setup_method(self):
        start = date(2025, 1, 6)
        constraint_date = start + timedelta(days=8)
        tasks = [
            make_task("1", "A", duration_days=5),
            make_task("2", "B", duration_days=5, constraint_type="SNET",
                      constraint_date=constraint_date),
        ]
        links = [make_link("1", "2")]
        self.version = ScheduleVersion(
            version_index=0, filename="test.mpp", project_start=start,
            tasks=tasks, links=links,
        )
        self.result = run_cpm(self.version)

    def test_project_duration(self):
        assert self.result.project_duration_days == 13.0

    def test_task_b_critical(self):
        assert self.result.task_floats["2"].is_critical

    def test_task_a_has_float(self):
        tf = self.result.task_floats["1"].total_float
        assert abs(tf - 3.0) < FLOAT_EPSILON, f"Task A TF={tf}, expected 3"


class TestNearCritical:
    def test_near_critical_not_flagged_below_threshold(self):
        version = parallel_path_schedule()
        result = run_cpm(version, near_critical_threshold=5.0)
        assert "3" not in result.near_critical
        assert "4" not in result.near_critical

    def test_near_critical_flagged_above_threshold(self):
        version = parallel_path_schedule()
        result = run_cpm(version, near_critical_threshold=10.0)
        assert "3" in result.near_critical
        assert "4" in result.near_critical


class TestCPMCycles:
    def test_cycle_detection(self):
        start = date(2025, 1, 6)
        tasks = [make_task("1", "A", duration_days=5), make_task("2", "B", duration_days=5)]
        links = [make_link("1", "2"), make_link("2", "1")]
        version = ScheduleVersion(
            version_index=0, filename="cyclic.mpp", project_start=start,
            tasks=tasks, links=links,
        )
        result = run_cpm(version)
        assert result.has_cycles is True
        assert len(result.cycle_tasks) > 0


class TestDrivingPath:
    def test_simple_chain_driving_path(self):
        version = simple_linear_schedule()
        result = trace_driving_path(version, "4")
        for uid in ("1", "2", "3", "4"):
            assert uid in result.driving_path

    def test_parallel_paths_driving_path(self):
        version = parallel_path_schedule()
        result = trace_driving_path(version, "5")
        assert "1" in result.driving_path or "2" in result.driving_path

    def test_driving_path_missing_task(self):
        version = simple_linear_schedule()
        result = trace_driving_path(version, "999")
        assert result.driving_path == []
        assert result.target_task_name == "[Task not found]"

    def test_driving_path_has_links(self):
        version = simple_linear_schedule()
        result = trace_driving_path(version, "4")
        assert len(result.driving_links) > 0
        for link in result.driving_links:
            assert link.is_driving is True

    def test_driving_path_full_trace(self):
        version = simple_linear_schedule()
        result = trace_driving_path(version, "4")
        assert len(result.full_trace) > 0
        for node in result.full_trace:
            assert "unique_id" in node
