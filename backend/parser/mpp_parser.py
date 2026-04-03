"""MPP Parser — MPXJ/JPype bridge for reading Microsoft Project .mpp files.

No data is sent externally; all parsing happens in-process.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── JVM state ─────────────────────────────────────────────────────────────────

JVM_AVAILABLE: bool = False
_jvm_started: bool = False
_UniversalProjectReader = None
_RelationType = None
_TimeUnit = None
_TaskField = None


def start_jvm() -> bool:
    """Start the JVM once at application startup.

    Returns True if JVM started successfully, False if Java is unavailable.
    Must be called before any parse_mpp() calls.

    IMPORTANT — classpath handling:
    The Python ``mpxj`` package registers all its JARs via
    ``jpype.addClassPath()`` at *import* time (inside mpxj/__init__.py).
    Those pre-registered paths are picked up automatically when
    ``jpype.startJVM()`` is called **without** an explicit ``classpath=``
    argument.  Passing ``classpath=jar_files`` to startJVM would *replace*
    (not extend) the accumulated classpath, which is why the JARs still
    appeared in ``jpype.getClassPath()`` but the ``net.sf.mpxj`` (now
    ``org.mpxj``) packages were not visible — the replacement classpath was
    processed differently by the JVM's class-path scanner.

    Also note: as of mpxj 13.x the Java package was renamed from
    ``net.sf.mpxj`` to ``org.mpxj``.  The bundled JAR must be inspected to
    confirm the correct namespace; do **not** hard-code ``net.sf.mpxj``.
    """
    global JVM_AVAILABLE, _jvm_started

    if _jvm_started:
        return JVM_AVAILABLE

    try:
        import jpype
        # Import mpxj BEFORE startJVM — its __init__.py calls
        # jpype.addClassPath() for every JAR in mpxj/lib/.  Those paths are
        # consumed by startJVM() when no explicit classpath= is passed.
        import mpxj as _mpxj_pkg  # noqa: F401 (side-effect: addClassPath)
        import jpype.imports  # registers Java TLD finders in sys.meta_path

        if not jpype.isJVMStarted():
            # Locate JVM — prefer explicit JAVA_HOME so portable JDK works
            jvm_path = None
            java_home = os.environ.get("JAVA_HOME", "")
            if java_home:
                for candidate in [
                    os.path.join(java_home, "bin", "server", "jvm.dll"),
                    os.path.join(java_home, "lib", "server", "libjvm.so"),
                    os.path.join(java_home, "lib", "server", "libjvm.dylib"),
                ]:
                    if os.path.isfile(candidate):
                        jvm_path = candidate
                        break

            logger.info(
                "Starting JVM: path=%s, classpath_entries=%d, JAVA_HOME=%s",
                jvm_path or "auto",
                len(jpype.getClassPath().split(os.pathsep)) if jpype.getClassPath() else 0,
                java_home or "not set",
            )

            # Do NOT pass classpath= here — let startJVM use the paths that
            # mpxj's __init__.py registered via addClassPath().
            if jvm_path:
                jpype.startJVM(jvm_path, convertStrings=False)
            else:
                jpype.startJVM(convertStrings=False)

        _load_mpxj_classes()
        JVM_AVAILABLE = True
        _jvm_started = True
        logger.info("JVM started successfully for MPXJ parsing")
        return True

    except Exception as exc:
        # Covers JVMNotFoundException, OSError (no libjvm), etc.
        _jvm_started = True  # don't retry
        JVM_AVAILABLE = False
        logger.warning(
            "Java runtime not available — .mpp parsing disabled. "
            "Install JDK 11+ and ensure JAVA_HOME is set. Error: %s",
            exc,
        )
        return False


def _load_mpxj_classes() -> None:
    """Import MPXJ Java classes after JVM is running.

    As of mpxj 13.x the Java package was renamed from ``net.sf.mpxj`` to
    ``org.mpxj``.  The Python ``mpxj`` wheel ships the new JAR, so we must
    use the ``org.mpxj`` namespace here.
    """
    global _UniversalProjectReader, _RelationType, _TimeUnit, _TaskField

    from org.mpxj.reader import UniversalProjectReader  # type: ignore[import]
    from org.mpxj import RelationType, TimeUnit  # type: ignore[import]

    _UniversalProjectReader = UniversalProjectReader
    _RelationType = RelationType
    _TimeUnit = TimeUnit


# ── Public API ────────────────────────────────────────────────────────────────


class ScheduleParseError(Exception):
    """Raised when MPXJ fails to parse a file."""


def parse_mpp(file_path: str, version_index: int = 0) -> dict[str, Any]:
    """Parse a .mpp file and return a dict matching the ScheduleVersion schema.

    Args:
        file_path: Absolute path to the .mpp file.
        version_index: Assigned index within the session.

    Returns:
        Dict suitable for ``ScheduleVersion(**result)``.

    Raises:
        ScheduleParseError: If parsing fails or Java is unavailable.
    """
    if not JVM_AVAILABLE:
        raise ScheduleParseError(
            "Java runtime not available. Install JDK 11+ and set JAVA_HOME."
        )

    if not os.path.exists(file_path):
        raise ScheduleParseError(f"File not found: {file_path}")

    try:
        import jpype

        def _blocking_parse() -> dict[str, Any]:
            return _do_parse(file_path, version_index)

        # Run synchronously (call from run_in_executor in async context)
        return _blocking_parse()

    except Exception as exc:
        # Wrap Java exceptions in our own type
        raise ScheduleParseError(f"Failed to parse {file_path}: {exc}") from exc


def _do_parse(file_path: str, version_index: int) -> dict[str, Any]:
    """Blocking parse — runs in a thread executor."""
    import jpype

    reader = _UniversalProjectReader()
    try:
        project = reader.read(file_path)
    except Exception as exc:
        raise ScheduleParseError(str(exc)) from exc

    props = project.getProjectProperties()
    status_date = _jdate(props.getStatusDate())
    project_start = _jdate(props.getStartDate())
    project_finish = _jdate(props.getFinishDate())
    filename = os.path.basename(file_path)

    tasks = []
    baselines = []

    for jtask in project.getTasks():
        if jtask is None:
            continue
        uid = str(jtask.getUniqueID())
        if uid == "0":  # project summary task
            continue

        task_dict = _extract_task(jtask)
        tasks.append(task_dict)

        bsl = _extract_baseline(jtask, uid)
        if bsl:
            baselines.append(bsl)

    links = _extract_links(project)

    return {
        "version_index": version_index,
        "filename": filename,
        "status_date": status_date.isoformat() if status_date else None,
        "project_start": project_start.isoformat() if project_start else None,
        "project_finish": project_finish.isoformat() if project_finish else None,
        "tasks": tasks,
        "links": links,
        "baselines": baselines,
        "extracted_at": datetime.utcnow().isoformat(),
    }


def _extract_task(jtask) -> dict[str, Any]:
    uid = str(jtask.getUniqueID())
    name = str(jtask.getName() or "")

    # Duration in days
    dur_obj = jtask.getDuration()
    duration_days = _duration_to_days(dur_obj)

    rem_dur_obj = jtask.getRemainingDuration()
    remaining_days = _duration_to_days(rem_dur_obj)

    pct = float(jtask.getPercentageComplete() or 0)

    actual_start = _jdate(jtask.getActualStart())
    actual_finish = _jdate(jtask.getActualFinish())
    early_start = _jdate(jtask.getEarlyStart())
    early_finish = _jdate(jtask.getEarlyFinish())
    late_start = _jdate(jtask.getLateStart())
    late_finish = _jdate(jtask.getLateFinish())

    # Float (stored in days by MPXJ)
    tf_obj = jtask.getTotalSlack()
    ff_obj = jtask.getFreeSlack()
    total_float = _duration_to_days(tf_obj)
    free_float = _duration_to_days(ff_obj)

    constraint_type = _constraint_type(jtask.getConstraintType())
    constraint_date = _jdate(jtask.getConstraintDate())

    is_critical = bool(jtask.getCritical())
    is_milestone = bool(jtask.getMilestone())
    is_summary = bool(jtask.getSummary())

    # LOE: check task type via string comparison
    task_type_str = str(jtask.getType() or "").upper()
    is_loe = "LOE" in task_type_str or "LEVEL" in task_type_str

    wbs = str(jtask.getWBS() or "")
    calendar = str(jtask.getCalendar().getName() if jtask.getCalendar() else "")

    # Resources
    resources = []
    for ra in jtask.getResourceAssignments():
        if ra and ra.getResource():
            rname = str(ra.getResource().getName() or "")
            if rname:
                resources.append(rname)

    # Baseline
    bsl_start = _jdate(jtask.getBaselineStart())
    bsl_finish = _jdate(jtask.getBaselineFinish())
    bsl_dur = _duration_to_days(jtask.getBaselineDuration())

    return {
        "unique_id": uid,
        "name": name,
        "duration_days": duration_days,
        "remaining_duration_days": remaining_days,
        "percent_complete": pct,
        "actual_start": actual_start.isoformat() if actual_start else None,
        "actual_finish": actual_finish.isoformat() if actual_finish else None,
        "early_start": early_start.isoformat() if early_start else None,
        "early_finish": early_finish.isoformat() if early_finish else None,
        "late_start": late_start.isoformat() if late_start else None,
        "late_finish": late_finish.isoformat() if late_finish else None,
        "total_float": total_float,
        "free_float": free_float,
        "constraint_type": constraint_type,
        "constraint_date": constraint_date.isoformat() if constraint_date else None,
        "is_critical": is_critical,
        "is_milestone": is_milestone,
        "is_summary": is_summary,
        "is_loe": is_loe,
        "wbs": wbs,
        "calendar_name": calendar or None,
        "resources": resources,
        "baseline_start": bsl_start.isoformat() if bsl_start else None,
        "baseline_finish": bsl_finish.isoformat() if bsl_finish else None,
        "baseline_duration_days": bsl_dur,
        "custom_fields": {},
    }


def _extract_baseline(jtask, uid: str) -> Optional[dict[str, Any]]:
    bsl_start = _jdate(jtask.getBaselineStart())
    bsl_finish = _jdate(jtask.getBaselineFinish())
    bsl_dur = _duration_to_days(jtask.getBaselineDuration())

    if bsl_start or bsl_finish or bsl_dur:
        return {
            "task_unique_id": uid,
            "baseline_start": bsl_start.isoformat() if bsl_start else None,
            "baseline_finish": bsl_finish.isoformat() if bsl_finish else None,
            "baseline_duration_days": bsl_dur,
            "baseline_work": None,
        }
    return None


def _extract_links(project) -> list[dict[str, Any]]:
    links = []
    seen = set()

    for jtask in project.getTasks():
        if jtask is None:
            continue
        succ_id = str(jtask.getUniqueID())
        if succ_id == "0":
            continue

        for pred_rel in jtask.getPredecessors():
            if pred_rel is None:
                continue
            pred_task = pred_rel.getPredecessorTask()
            if pred_task is None:
                continue
            pred_id = str(pred_task.getUniqueID())
            if pred_id == "0":
                continue

            key = (pred_id, succ_id)
            if key in seen:
                continue
            seen.add(key)

            rel_type = _relation_type(pred_rel.getType())
            lag_obj = pred_rel.getLag()
            lag_days = _duration_to_days(lag_obj) or 0.0

            links.append(
                {
                    "pred_unique_id": pred_id,
                    "succ_unique_id": succ_id,
                    "relationship_type": rel_type,
                    "lag_days": lag_days,
                }
            )

    return links


# ── Helper converters ─────────────────────────────────────────────────────────


def _jdate(jdate_val) -> Optional[date]:
    """Convert a Java Date / LocalDate to Python date."""
    if jdate_val is None:
        return None
    try:
        # Try getTime() (java.util.Date) first
        epoch_ms = int(jdate_val.getTime())
        return date.fromtimestamp(epoch_ms / 1000.0)
    except Exception:
        pass
    try:
        # Try toLocalDate() for LocalDate objects
        ld = jdate_val.toLocalDate()
        return date(int(ld.getYear()), int(ld.getMonthValue()), int(ld.getDayOfMonth()))
    except Exception:
        return None


def _duration_to_days(dur_obj) -> Optional[float]:
    """Convert an MPXJ Duration object to float days."""
    if dur_obj is None:
        return None
    try:
        if _TimeUnit is not None:
            return float(dur_obj.convertUnits(_TimeUnit.DAYS, None).getDuration())
        # Fallback: assume stored in days
        return float(dur_obj.getDuration())
    except Exception:
        return None


def _relation_type(rel_type_val) -> str:
    """Map MPXJ RelationType to 'FS'/'SS'/'FF'/'SF'."""
    if rel_type_val is None:
        return "FS"
    name = str(rel_type_val.name() if hasattr(rel_type_val, "name") else rel_type_val).upper()
    mapping = {"FINISH_START": "FS", "START_START": "SS", "FINISH_FINISH": "FF", "START_FINISH": "SF"}
    # Also handle short names
    for k, v in {"FS": "FS", "SS": "SS", "FF": "FF", "SF": "SF"}.items():
        if name == k:
            return v
    for k, v in mapping.items():
        if k in name:
            return v
    return "FS"


def _constraint_type(ct_val) -> str:
    """Map MPXJ ConstraintType to schema string."""
    if ct_val is None:
        return "ASAP"
    name = str(ct_val.name() if hasattr(ct_val, "name") else ct_val).upper()
    mapping = {
        "AS_SOON_AS_POSSIBLE": "ASAP",
        "AS_LATE_AS_POSSIBLE": "ALAP",
        "MUST_START_ON": "MSO",
        "MUST_FINISH_ON": "MFO",
        "START_NO_EARLIER_THAN": "SNET",
        "START_NO_LATER_THAN": "SNLT",
        "FINISH_NO_EARLIER_THAN": "FNET",
        "FINISH_NO_LATER_THAN": "FNLT",
    }
    for k, v in mapping.items():
        if k in name:
            return v
    return "ASAP"
