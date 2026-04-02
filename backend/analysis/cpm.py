"""CPM Engine — Forward/backward pass, float calculation, critical path."""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import networkx as nx

from backend.models.schemas import CPMResult, ScheduleVersion, TaskFloat

logger = logging.getLogger(__name__)

FLOAT_EPSILON = 0.001  # days

EARLY_CONSTRAINTS = {"SNET", "MSO", "FNET"}
LATE_CONSTRAINTS = {"SNLT", "MFO", "FNLT"}


def run_cpm(
    version: ScheduleVersion,
    near_critical_threshold: float = 5.0,
) -> CPMResult:
    """Run CPM on a ScheduleVersion and return a CPMResult."""
    project_start = version.project_start or date.today()
    G = _build_graph(version)

    if not nx.is_directed_acyclic_graph(G):
        cycle_nodes = list(nx.find_cycle(G))
        cycle_ids = [n for edge in cycle_nodes for n in edge]
        return CPMResult(
            version_index=version.version_index,
            has_cycles=True,
            cycle_tasks=list(set(cycle_ids)),
        )

    task_map = {t.unique_id: t for t in version.tasks}

    _forward_pass(G, task_map, project_start)
    _backward_pass(G, task_map, project_start)

    task_floats: dict[str, TaskFloat] = {}
    for node in G.nodes:
        if node in ("__START__", "__END__"):
            continue
        task = task_map.get(node)
        if task is None:
            continue

        nd = G.nodes[node]
        ef = nd.get("EF", 0.0)
        lf = nd.get("LF", 0.0)
        tf = lf - ef
        ff = _compute_free_float(G, node)

        is_critical = tf <= FLOAT_EPSILON
        is_near_critical = tf <= near_critical_threshold

        task_floats[node] = TaskFloat(
            unique_id=node,
            total_float=round(tf, 4),
            free_float=round(ff, 4),
            is_critical=is_critical,
            is_near_critical=is_near_critical,
        )

    critical_path = _extract_critical_path(G, task_floats)
    near_critical = [uid for uid, tf in task_floats.items() if tf.is_near_critical]

    # project_duration = max EF across all non-sentinel nodes
    project_duration = max(
        (G.nodes[n].get("EF", 0.0) for n in G.nodes if n not in ("__START__", "__END__")),
        default=0.0,
    )

    return CPMResult(
        version_index=version.version_index,
        task_floats=task_floats,
        critical_path=critical_path,
        near_critical=near_critical,
        project_duration_days=project_duration,
        has_cycles=False,
    )


def _build_graph(version: ScheduleVersion) -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_node("__START__", ES=0.0, EF=0.0, LS=0.0, LF=0.0)
    G.add_node("__END__", ES=0.0, EF=0.0, LS=0.0, LF=0.0)

    task_ids = set()
    for task in version.tasks:
        if task.is_summary or task.is_loe:
            continue
        task_ids.add(task.unique_id)
        G.add_node(task.unique_id, ES=0.0, EF=task.duration_days, LS=0.0, LF=task.duration_days)

    has_pred: set[str] = set()
    has_succ: set[str] = set()

    for link in version.links:
        p, s = link.pred_unique_id, link.succ_unique_id
        if p not in task_ids or s not in task_ids:
            continue
        G.add_edge(p, s, rel_type=link.relationship_type, lag=link.lag_days)
        has_pred.add(s)
        has_succ.add(p)

    for tid in task_ids:
        if tid not in has_pred:
            G.add_edge("__START__", tid, rel_type="FS", lag=0.0)
        if tid not in has_succ:
            G.add_edge(tid, "__END__", rel_type="FS", lag=0.0)

    return G


def _forward_pass(G: nx.DiGraph, task_map: dict, project_start: date) -> None:
    for node in nx.topological_sort(G):
        if node == "__START__":
            G.nodes[node]["ES"] = 0.0
            G.nodes[node]["EF"] = 0.0
            continue

        task = task_map.get(node)
        dur = task.duration_days if task else 0.0
        es_candidates: list[float] = [0.0]

        for pred, _, data in G.in_edges(node, data=True):
            rel = data.get("rel_type", "FS")
            lag = data.get("lag", 0.0)
            pred_ES = G.nodes[pred]["ES"]
            pred_EF = G.nodes[pred]["EF"]

            if rel == "FS":
                es_candidates.append(pred_EF + lag)
            elif rel == "SS":
                es_candidates.append(pred_ES + lag)
            elif rel == "FF":
                es_candidates.append(pred_EF + lag - dur)
            elif rel == "SF":
                es_candidates.append(pred_ES + lag - dur)

        es = max(es_candidates)

        if task and task.constraint_type in EARLY_CONSTRAINTS and task.constraint_date:
            constraint_days = float((task.constraint_date - project_start).days)
            if task.constraint_type in ("SNET", "MSO"):
                es = max(es, constraint_days)
            elif task.constraint_type == "FNET":
                es = max(es, constraint_days - dur)

        G.nodes[node]["ES"] = es
        G.nodes[node]["EF"] = es + dur


def _backward_pass(G: nx.DiGraph, task_map: dict, project_start: date) -> None:
    project_end = 0.0
    for node in G.nodes:
        project_end = max(project_end, G.nodes[node].get("EF", 0.0))

    G.nodes["__END__"]["LF"] = project_end
    G.nodes["__END__"]["LS"] = project_end

    for node in reversed(list(nx.topological_sort(G))):
        if node == "__END__":
            continue

        task = task_map.get(node)
        dur = task.duration_days if task else 0.0
        lf_candidates: list[float] = [project_end]

        for _, succ, data in G.out_edges(node, data=True):
            rel = data.get("rel_type", "FS")
            lag = data.get("lag", 0.0)
            succ_LS = G.nodes[succ]["LS"]
            succ_LF = G.nodes[succ]["LF"]

            if rel == "FS":
                lf_candidates.append(succ_LS - lag)
            elif rel == "SS":
                lf_candidates.append(succ_LS - lag + dur)
            elif rel == "FF":
                lf_candidates.append(succ_LF - lag)
            elif rel == "SF":
                succ_task = task_map.get(succ)
                succ_dur = succ_task.duration_days if succ_task else 0.0
                lf_candidates.append(succ_LF - lag - succ_dur + dur)

        lf = min(lf_candidates)

        if task and task.constraint_type in LATE_CONSTRAINTS and task.constraint_date:
            constraint_days = float((task.constraint_date - project_start).days)
            if task.constraint_type in ("MFO", "FNLT"):
                lf = min(lf, constraint_days)
            elif task.constraint_type == "SNLT":
                lf = min(lf, constraint_days + dur)

        G.nodes[node]["LF"] = lf
        G.nodes[node]["LS"] = lf - dur

    start_ls = [G.nodes[s]["LS"] for _, s, _ in G.out_edges("__START__", data=True)]
    if start_ls:
        G.nodes["__START__"]["LS"] = min(start_ls)
        G.nodes["__START__"]["LF"] = min(start_ls)


def _compute_free_float(G: nx.DiGraph, node: str) -> float:
    ef = G.nodes[node].get("EF", 0.0)
    es = G.nodes[node].get("ES", 0.0)
    ff_candidates: list[float] = []

    for _, succ, data in G.out_edges(node, data=True):
        if succ == "__END__":
            continue
        rel = data.get("rel_type", "FS")
        lag = data.get("lag", 0.0)
        succ_ES = G.nodes[succ].get("ES", 0.0)
        succ_EF = G.nodes[succ].get("EF", 0.0)

        if rel == "FS":
            ff_candidates.append(succ_ES - lag - ef)
        elif rel == "SS":
            ff_candidates.append(succ_ES - lag - es)
        elif rel == "FF":
            ff_candidates.append(succ_EF - lag - ef)

    return min(ff_candidates) if ff_candidates else 0.0


def _extract_critical_path(
    G: nx.DiGraph,
    task_floats: dict[str, TaskFloat],
) -> list[str]:
    critical_ids = {uid for uid, tf in task_floats.items() if tf.is_critical}
    path: list[str] = []
    visited: set[str] = set()

    def _dfs(node: str) -> bool:
        if node == "__END__":
            return True
        if node in visited:
            return False
        visited.add(node)

        successors = sorted(
            [(s, d) for _, s, d in G.out_edges(node, data=True)],
            key=lambda x: G.nodes[x[0]].get("ES", 0),
        )
        for succ, _ in successors:
            if succ == "__END__" or succ in critical_ids:
                if succ != "__END__":
                    path.append(succ)
                if _dfs(succ):
                    return True
                if succ != "__END__":
                    path.pop()

        return False

    _dfs("__START__")
    return path


def get_graph(version: ScheduleVersion) -> nx.DiGraph:
    """Build and return CPM graph with ES/EF/LS/LF populated."""
    project_start = version.project_start or date.today()
    task_map = {t.unique_id: t for t in version.tasks}
    G = _build_graph(version)
    if not nx.is_directed_acyclic_graph(G):
        return G
    _forward_pass(G, task_map, project_start)
    _backward_pass(G, task_map, project_start)
    return G
