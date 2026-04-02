"""Tests for the diff engine."""

from __future__ import annotations

import pytest

from backend.analysis.diff_engine import build_diff_matrix, diff_versions
from backend.tests.synthetic.schedule_factory import (
    multi_version_pair,
    simple_linear_schedule,
)


class TestDiffVersions:
    def setup_method(self):
        self.v0, self.v1 = multi_version_pair()
        self.diff = diff_versions(self.v0, self.v1)

    def test_version_indices(self):
        assert self.diff.base_version_index == 0
        assert self.diff.compare_version_index == 1

    def test_task_added_detected(self):
        added = [c for c in self.diff.task_changes if c.change_type == "added"]
        added_ids = {c.unique_id for c in added}
        assert "4" in added_ids  # Task D was added in v1

    def test_task_removed_detected(self):
        removed = [c for c in self.diff.task_changes if c.change_type == "removed"]
        removed_ids = {c.unique_id for c in removed}
        assert "3" in removed_ids  # Task C was removed in v1

    def test_task_duration_change_detected(self):
        modified = [c for c in self.diff.task_changes if c.change_type == "modified" and c.unique_id == "2"]
        assert len(modified) == 1
        change = modified[0]
        assert "duration_days" in change.field_changes
        old_dur, new_dur = change.field_changes["duration_days"]
        assert old_dur == 5.0
        assert new_dur == 8.0

    def test_duration_delta_computed(self):
        modified = [c for c in self.diff.task_changes if c.change_type == "modified" and c.unique_id == "2"]
        assert modified[0].duration_delta == 3.0

    def test_link_lag_change_detected(self):
        modified_links = [c for c in self.diff.link_changes if c.change_type == "modified"]
        assert len(modified_links) >= 1
        # Link 1->2 had lag added
        lag_changed = [c for c in modified_links if c.pred_unique_id == "1" and c.succ_unique_id == "2"]
        assert len(lag_changed) == 1
        old_lag, new_lag = lag_changed[0].field_changes["lag_days"]
        assert old_lag == 0.0
        assert new_lag == 2.0

    def test_link_removed_detected(self):
        removed_links = [c for c in self.diff.link_changes if c.change_type == "removed"]
        # Link 2->3 was removed (task 3 removed means links to/from it also gone)
        removed_pairs = {(c.pred_unique_id, c.succ_unique_id) for c in removed_links}
        assert ("2", "3") in removed_pairs or ("3", "99") in removed_pairs

    def test_link_added_detected(self):
        added_links = [c for c in self.diff.link_changes if c.change_type == "added"]
        added_pairs = {(c.pred_unique_id, c.succ_unique_id) for c in added_links}
        # Link 2->4 and 4->99 were added
        assert ("2", "4") in added_pairs or ("4", "99") in added_pairs

    def test_total_task_changes(self):
        assert self.diff.total_task_changes >= 2  # at minimum added + removed


class TestDiffWithCPMData:
    def test_float_delta_computed_when_cpm_provided(self):
        from backend.analysis.cpm import run_cpm

        v0, v1 = multi_version_pair()
        cpm0 = run_cpm(v0)
        cpm1 = run_cpm(v1)
        diff = diff_versions(v0, v1, base_cpm=cpm0, compare_cpm=cpm1)

        # Check that float_delta is populated for tasks present in both versions
        modified = [c for c in diff.task_changes if c.change_type == "modified" and c.unique_id == "2"]
        if modified:
            assert modified[0].float_delta is not None

    def test_project_duration_delta_from_cpm(self):
        from backend.analysis.cpm import run_cpm

        v0, v1 = multi_version_pair()
        cpm0 = run_cpm(v0)
        cpm1 = run_cpm(v1)
        diff = diff_versions(v0, v1, base_cpm=cpm0, compare_cpm=cpm1)

        assert diff.project_finish_delta_days is not None

    def test_project_finish_delta_from_dates(self):
        v0, v1 = multi_version_pair()
        diff = diff_versions(v0, v1)
        # v0 finishes 15 days after start, v1 finishes 20 days after start → delta = 5
        assert diff.project_finish_delta_days == 5.0


class TestIdenticalVersions:
    def test_no_changes_for_identical_versions(self):
        v0 = simple_linear_schedule(version_index=0)
        v1 = simple_linear_schedule(version_index=1)
        # Make v1 the same tasks/links as v0
        from backend.models.schemas import ScheduleVersion
        v1_same = ScheduleVersion(
            version_index=1,
            filename=v1.filename,
            status_date=v0.status_date,
            project_start=v0.project_start,
            project_finish=v0.project_finish,
            tasks=v0.tasks[:],
            links=v0.links[:],
        )
        diff = diff_versions(v0, v1_same)
        assert diff.total_task_changes == 0
        assert len(diff.link_changes) == 0


class TestDiffMatrix:
    def test_build_diff_matrix_3_versions(self):
        from backend.tests.synthetic.schedule_factory import forensics_multi_version
        versions = forensics_multi_version()
        matrix = build_diff_matrix(versions)

        # 3 versions → C(3,2) = 3 pairs
        assert len(matrix) == 3

        # Pairs: (0,1), (0,2), (1,2)
        pairs = {(d.base_version_index, d.compare_version_index) for d in matrix}
        assert (0, 1) in pairs
        assert (0, 2) in pairs
        assert (1, 2) in pairs

    def test_build_diff_matrix_2_versions(self):
        v0, v1 = multi_version_pair()
        matrix = build_diff_matrix([v0, v1])
        assert len(matrix) == 1
        assert matrix[0].base_version_index == 0
        assert matrix[0].compare_version_index == 1


class TestLinkDiff:
    def test_link_relationship_type_change(self):
        from backend.models.schemas import ScheduleVersion
        from backend.tests.synthetic.schedule_factory import make_link, make_task
        from datetime import date

        start = date(2025, 1, 6)
        tasks = [make_task("1", "A", duration_days=5), make_task("2", "B", duration_days=5)]
        v0 = ScheduleVersion(
            version_index=0, filename="v0.mpp", project_start=start,
            tasks=tasks, links=[make_link("1", "2", rel="FS")],
        )
        v1 = ScheduleVersion(
            version_index=1, filename="v1.mpp", project_start=start,
            tasks=tasks, links=[make_link("1", "2", rel="SS")],
        )
        diff = diff_versions(v0, v1)
        modified_links = [c for c in diff.link_changes if c.change_type == "modified"]
        assert len(modified_links) == 1
        old_rel, new_rel = modified_links[0].field_changes["relationship_type"]
        assert old_rel == "FS"
        assert new_rel == "SS"
