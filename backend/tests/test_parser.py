"""Tests for MPP parser data model and synthetic factory.

These tests validate:
1. Pydantic schema round-trips
2. Synthetic schedule factory produces valid ScheduleVersion objects
3. Parser helper functions work correctly (without Java/JVM dependency)
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.models.schemas import (
    Baseline,
    Link,
    ScheduleVersion,
    Task,
)
from backend.tests.synthetic.schedule_factory import (
    dcma_violations_schedule,
    forensics_multi_version,
    make_baseline,
    make_link,
    make_task,
    multi_version_pair,
    parallel_path_schedule,
    simple_linear_schedule,
)


# ── Schema round-trip tests ───────────────────────────────────────────────────


class TestSchemas:
    def test_task_defaults(self):
        t = Task(unique_id="1", name="Test Task")
        assert t.unique_id == "1"
        assert t.name == "Test Task"
        assert t.duration_days == 0.0
        assert t.percent_complete == 0.0
        assert t.constraint_type == "ASAP"
        assert t.is_critical is False
        assert t.resources == []
        assert t.custom_fields == {}

    def test_task_with_all_fields(self):
        t = make_task(
            "42",
            "Full Task",
            duration_days=10.0,
            percent_complete=50.0,
            is_critical=True,
            total_float=0.0,
            free_float=0.0,
            resources=["Alice", "Bob"],
            actual_start=date(2025, 1, 6),
            actual_finish=None,
        )
        assert t.unique_id == "42"
        assert t.duration_days == 10.0
        assert t.percent_complete == 50.0
        assert t.is_critical is True
        assert t.resources == ["Alice", "Bob"]

    def test_link_defaults(self):
        lnk = Link(pred_unique_id="1", succ_unique_id="2")
        assert lnk.relationship_type == "FS"
        assert lnk.lag_days == 0.0

    def test_link_with_lead(self):
        lnk = make_link("1", "2", rel="FS", lag=-3.0)
        assert lnk.lag_days == -3.0
        assert lnk.relationship_type == "FS"

    def test_link_ss_with_lag(self):
        lnk = make_link("1", "2", rel="SS", lag=2.0)
        assert lnk.relationship_type == "SS"
        assert lnk.lag_days == 2.0

    def test_baseline_optional_fields(self):
        b = make_baseline("5", start=date(2025, 1, 1), duration_days=10.0)
        assert b.task_unique_id == "5"
        assert b.baseline_start == date(2025, 1, 1)
        assert b.baseline_duration_days == 10.0
        assert b.baseline_finish is None

    def test_schedule_version_serialisation(self):
        v = simple_linear_schedule()
        data = v.model_dump()
        v2 = ScheduleVersion(**data)
        assert v2.version_index == v.version_index
        assert len(v2.tasks) == len(v.tasks)
        assert len(v2.links) == len(v.links)

    def test_schedule_version_json_round_trip(self):
        v = simple_linear_schedule()
        json_str = v.model_dump_json()
        assert '"version_index"' in json_str
        v2 = ScheduleVersion.model_validate_json(json_str)
        assert v2.filename == v.filename


# ── Synthetic factory tests ───────────────────────────────────────────────────


class TestSyntheticFactory:
    def test_simple_linear_schedule_structure(self):
        v = simple_linear_schedule()
        assert v.version_index == 0
        assert len(v.tasks) == 4
        assert len(v.links) == 3

        task_ids = {t.unique_id for t in v.tasks}
        assert {"1", "2", "3", "4"} == task_ids

        milestone = next(t for t in v.tasks if t.unique_id == "4")
        assert milestone.is_milestone is True
        assert milestone.duration_days == 0.0

    def test_simple_linear_schedule_links(self):
        v = simple_linear_schedule()
        link_pairs = {(lnk.pred_unique_id, lnk.succ_unique_id) for lnk in v.links}
        assert ("1", "2") in link_pairs
        assert ("2", "3") in link_pairs
        assert ("3", "4") in link_pairs

    def test_parallel_path_schedule(self):
        v = parallel_path_schedule()
        assert len(v.tasks) == 5
        assert len(v.links) == 4
        milestone = next(t for t in v.tasks if t.unique_id == "5")
        assert milestone.is_milestone is True

    def test_dcma_violations_schedule(self):
        v = dcma_violations_schedule()
        task_map = {t.unique_id: t for t in v.tasks}

        # Orphan task
        assert "10" in task_map

        # Hard constraint
        assert task_map["5"].constraint_type == "MSO"

        # No resources
        assert task_map["9"].resources == []

        # Long duration
        assert task_map["8"].duration_days == 50

        # Lead (negative lag)
        lead_links = [lnk for lnk in v.links if lnk.lag_days < 0]
        assert len(lead_links) == 1
        assert lead_links[0].lag_days == -2.0

        # Positive lag
        lag_links = [lnk for lnk in v.links if lnk.lag_days > 0]
        assert len(lag_links) == 1
        assert lag_links[0].lag_days == 5.0

    def test_multi_version_pair_structure(self):
        v0, v1 = multi_version_pair()
        assert v0.version_index == 0
        assert v1.version_index == 1

        v0_ids = {t.unique_id for t in v0.tasks}
        v1_ids = {t.unique_id for t in v1.tasks}

        # Task 3 removed in v1
        assert "3" in v0_ids
        assert "3" not in v1_ids

        # Task 4 added in v1
        assert "4" not in v0_ids
        assert "4" in v1_ids

    def test_multi_version_pair_changes(self):
        v0, v1 = multi_version_pair()

        v0_task2 = next(t for t in v0.tasks if t.unique_id == "2")
        v1_task2 = next(t for t in v1.tasks if t.unique_id == "2")

        # Duration changed
        assert v0_task2.duration_days == 5.0
        assert v1_task2.duration_days == 8.0

        # Lag added on link 1->2
        v0_link = next(lnk for lnk in v0.links if lnk.pred_unique_id == "1")
        v1_link = next(lnk for lnk in v1.links if lnk.pred_unique_id == "1")
        assert v0_link.lag_days == 0.0
        assert v1_link.lag_days == 2.0

    def test_forensics_multi_version_baseline_tamper(self):
        versions = forensics_multi_version()
        assert len(versions) == 3

        v0_t2 = next(t for t in versions[0].tasks if t.unique_id == "2")
        v1_t2 = next(t for t in versions[1].tasks if t.unique_id == "2")

        # Baseline start changed between v0 and v1
        assert v0_t2.baseline_start != v1_t2.baseline_start

    def test_forensics_multi_version_actuals_rewrite(self):
        versions = forensics_multi_version()
        v0_t1 = next(t for t in versions[0].tasks if t.unique_id == "1")
        v1_t1 = next(t for t in versions[1].tasks if t.unique_id == "1")

        assert v0_t1.percent_complete == 100.0
        assert v1_t1.percent_complete == 100.0
        assert v0_t1.actual_finish != v1_t1.actual_finish

    def test_forensics_multi_version_constraint_pinning(self):
        versions = forensics_multi_version()
        v1_t3 = next(t for t in versions[1].tasks if t.unique_id == "3")
        v2_t3 = next(t for t in versions[2].tasks if t.unique_id == "3")

        assert v1_t3.constraint_type == "ASAP"
        assert v2_t3.constraint_type == "MSO"

    def test_forensics_multi_version_logic_deletion(self):
        versions = forensics_multi_version()
        v1_links = {(lnk.pred_unique_id, lnk.succ_unique_id) for lnk in versions[1].links}
        v2_links = {(lnk.pred_unique_id, lnk.succ_unique_id) for lnk in versions[2].links}

        assert ("3", "5") in v1_links
        assert ("3", "5") not in v2_links

    def test_forensics_duration_smoothing(self):
        versions = forensics_multi_version()
        durs = [
            next(t for t in v.tasks if t.unique_id == "4").duration_days
            for v in versions
        ]
        # Should decrease uniformly: 15, 10, 5
        deltas = [durs[i] - durs[i + 1] for i in range(len(durs) - 1)]
        assert all(d == deltas[0] for d in deltas), f"Not uniform: {durs}"


# ── Parser module tests (no JVM required) ────────────────────────────────────


class TestParserModule:
    def test_jvm_available_flag_exists(self):
        from backend.parser import mpp_parser

        assert isinstance(mpp_parser.JVM_AVAILABLE, bool)

    def test_parse_mpp_raises_when_jvm_unavailable(self, monkeypatch):
        from backend.parser import mpp_parser

        monkeypatch.setattr(mpp_parser, "JVM_AVAILABLE", False)
        with pytest.raises(mpp_parser.ScheduleParseError, match="Java runtime"):
            mpp_parser.parse_mpp("/nonexistent/path.mpp")

    def test_parse_mpp_raises_for_missing_file(self, monkeypatch):
        from backend.parser import mpp_parser

        monkeypatch.setattr(mpp_parser, "JVM_AVAILABLE", True)
        with pytest.raises(mpp_parser.ScheduleParseError, match="not found"):
            mpp_parser.parse_mpp("/nonexistent/path.mpp")

    def test_relation_type_mapping(self):
        from backend.parser.mpp_parser import _relation_type

        class FakeRelType:
            def __init__(self, name):
                self._name = name

            def name(self):
                return self._name

        assert _relation_type(FakeRelType("FINISH_START")) == "FS"
        assert _relation_type(FakeRelType("START_START")) == "SS"
        assert _relation_type(FakeRelType("FINISH_FINISH")) == "FF"
        assert _relation_type(FakeRelType("START_FINISH")) == "SF"
        assert _relation_type(None) == "FS"

    def test_constraint_type_mapping(self):
        from backend.parser.mpp_parser import _constraint_type

        class FakeConstraintType:
            def __init__(self, name):
                self._name = name

            def name(self):
                return self._name

        assert _constraint_type(FakeConstraintType("AS_SOON_AS_POSSIBLE")) == "ASAP"
        assert _constraint_type(FakeConstraintType("MUST_START_ON")) == "MSO"
        assert _constraint_type(FakeConstraintType("START_NO_EARLIER_THAN")) == "SNET"
        assert _constraint_type(None) == "ASAP"
