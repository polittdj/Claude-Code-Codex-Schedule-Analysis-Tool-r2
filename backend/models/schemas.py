"""Pydantic v2 data models for Schedule Forensics Tool."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


REL_TYPES = Literal["FS", "SS", "FF", "SF"]

CONSTRAINT_TYPES = Literal[
    "ASAP", "ALAP", "MSO", "MFO", "SNET", "SNLT", "FNET", "FNLT"
]


class Task(BaseModel):
    unique_id: str
    name: str
    duration_days: float = 0.0
    remaining_duration_days: float = 0.0
    percent_complete: float = 0.0
    actual_start: Optional[date] = None
    actual_finish: Optional[date] = None
    early_start: Optional[date] = None
    early_finish: Optional[date] = None
    late_start: Optional[date] = None
    late_finish: Optional[date] = None
    total_float: Optional[float] = None
    free_float: Optional[float] = None
    constraint_type: CONSTRAINT_TYPES = "ASAP"
    constraint_date: Optional[date] = None
    is_critical: bool = False
    is_milestone: bool = False
    is_summary: bool = False
    is_loe: bool = False
    wbs: str = ""
    calendar_name: Optional[str] = None
    resources: list[str] = Field(default_factory=list)
    baseline_start: Optional[date] = None
    baseline_finish: Optional[date] = None
    baseline_duration_days: Optional[float] = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class Link(BaseModel):
    pred_unique_id: str
    succ_unique_id: str
    relationship_type: REL_TYPES = "FS"
    lag_days: float = 0.0  # negative = lead


class Baseline(BaseModel):
    task_unique_id: str
    baseline_start: Optional[date] = None
    baseline_finish: Optional[date] = None
    baseline_duration_days: Optional[float] = None
    baseline_work: Optional[float] = None


class ScheduleVersion(BaseModel):
    version_index: int
    filename: str
    status_date: Optional[date] = None
    project_start: Optional[date] = None
    project_finish: Optional[date] = None
    tasks: list[Task] = Field(default_factory=list)
    links: list[Link] = Field(default_factory=list)
    baselines: list[Baseline] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class Session(BaseModel):
    session_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    versions: list[ScheduleVersion] = Field(default_factory=list)
    upload_paths: list[str] = Field(default_factory=list)


# ── Analysis result models ────────────────────────────────────────────────────


class TaskFloat(BaseModel):
    unique_id: str
    total_float: float
    free_float: float
    is_critical: bool
    is_near_critical: bool


class CPMResult(BaseModel):
    version_index: int
    task_floats: dict[str, TaskFloat] = Field(default_factory=dict)
    critical_path: list[str] = Field(default_factory=list)
    near_critical: list[str] = Field(default_factory=list)
    project_duration_days: Optional[float] = None
    has_cycles: bool = False
    cycle_tasks: list[str] = Field(default_factory=list)


class DrivingPathLink(BaseModel):
    pred_unique_id: str
    succ_unique_id: str
    relationship_type: REL_TYPES
    lag_days: float
    pred_name: str = ""
    succ_name: str = ""
    is_driving: bool = True


class DrivingPathResult(BaseModel):
    target_task_id: str
    target_task_name: str
    driving_path: list[str]
    driving_links: list[DrivingPathLink]
    full_trace: list[dict[str, Any]] = Field(default_factory=list)


class TaskChange(BaseModel):
    unique_id: str
    name: str
    change_type: Literal["added", "removed", "modified"]
    field_changes: dict[str, tuple[Any, Any]] = Field(default_factory=dict)
    float_delta: Optional[float] = None
    duration_delta: Optional[float] = None
    critical_path_change: Optional[str] = None


class LinkChange(BaseModel):
    pred_unique_id: str
    succ_unique_id: str
    change_type: Literal["added", "removed", "modified"]
    field_changes: dict[str, tuple[Any, Any]] = Field(default_factory=dict)


class VersionDiff(BaseModel):
    base_version_index: int
    compare_version_index: int
    task_changes: list[TaskChange] = Field(default_factory=list)
    link_changes: list[LinkChange] = Field(default_factory=list)
    project_finish_delta_days: Optional[float] = None
    critical_path_length_delta: Optional[float] = None
    new_critical_task_count: int = 0
    removed_critical_task_count: int = 0
    total_task_changes: int = 0


class DCMAMetric(BaseModel):
    metric_id: int
    name: str
    value: Optional[float] = None
    count: int = 0
    denominator: int = 0
    threshold_warn: Optional[float] = None
    threshold_fail: Optional[float] = None
    status: Literal["pass", "warn", "fail", "info"] = "info"
    affected_task_ids: list[str] = Field(default_factory=list)
    notes: str = ""


class DCMAResult(BaseModel):
    version_index: int
    metrics: list[DCMAMetric] = Field(default_factory=list)
    overall_status: Literal["pass", "warn", "fail"] = "pass"


class NASACheck(BaseModel):
    check_id: str
    name: str
    passed: bool
    details: str = ""
    affected_task_ids: list[str] = Field(default_factory=list)


class NASAResult(BaseModel):
    version_index: int
    checks: list[NASACheck] = Field(default_factory=list)
    overall_passed: bool = True


class ForensicFinding(BaseModel):
    pattern: str
    severity: Literal["HIGH", "MEDIUM", "LOW"]
    affected_task_ids: list[str] = Field(default_factory=list)
    affected_link_pairs: list[tuple[str, str]] = Field(default_factory=list)
    evidence: str
    confidence: float
    version_indices: list[int] = Field(default_factory=list)


class ForensicsResult(BaseModel):
    version_indices: list[int]
    findings: list[ForensicFinding] = Field(default_factory=list)
    manipulation_risk_score: float = 0.0
