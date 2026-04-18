"""
Analysis helpers: per-joint statistics, phase detection, comparison utilities.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import numpy as np

from .parser import LogData, Frame, StateSegment, JOINTS_21, VECTOR_FIELDS, SCALAR_FIELDS


@dataclass
class JointStats:
    name: str
    field: str
    mean: float
    std: float
    min_val: float
    max_val: float
    count: int


def compute_joint_stats(
    log: LogData,
    field: str = "tau_",
    state_filter: Optional[List[str]] = None,
) -> List[JointStats]:
    """
    Compute per-joint statistics for a vector field over the given state filter.
    Returns list ordered by JOINTS_21 index.
    """
    results: List[JointStats] = []
    for jname in JOINTS_21:
        ts, vals = log.get_series(field, jname, state_filter)
        if not vals:
            results.append(JointStats(jname, field, 0, 0, 0, 0, 0))
            continue
        arr = np.array(vals, dtype=float)
        results.append(JointStats(
            name=jname,
            field=field,
            mean=float(np.mean(arr)),
            std=float(np.std(arr)),
            min_val=float(np.min(arr)),
            max_val=float(np.max(arr)),
            count=len(arr),
        ))
    return results


def compute_body_stats(
    log: LogData,
    field: str,
    state_filter: Optional[List[str]] = None,
) -> Dict[str, JointStats]:
    """Return {joint_name: JointStats} dict."""
    stats_list = compute_joint_stats(log, field, state_filter)
    return {s.name: s for s in stats_list}


def compute_scalar_stats(
    log: LogData,
    field: str,          # e.g. "rpy"
    component: int = 0,  # 0=roll,1=pitch,2=yaw
    state_filter: Optional[List[str]] = None,
) -> Optional[JointStats]:
    """Stats for a scalar-group component."""
    ts, vals = log.get_series(field, str(component), state_filter)
    if not vals:
        return None
    arr = np.array(vals, dtype=float)
    return JointStats(
        name=f"{field}[{component}]",
        field=field,
        mean=float(np.mean(arr)),
        std=float(np.std(arr)),
        min_val=float(np.min(arr)),
        max_val=float(np.max(arr)),
        count=len(arr),
    )


def get_state_segments_for_filter(
    log: LogData, state_filter: List[str]
) -> List[StateSegment]:
    return [s for s in log.state_segments if s.state in state_filter]


def downsample(ts: List[float], vals: List[float], max_points: int = 4000
               ) -> Tuple[List[float], List[float]]:
    """Downsample a time series to at most max_points for fast plotting."""
    n = len(ts)
    if n <= max_points:
        return ts, vals
    step = max(1, n // max_points)
    return ts[::step], vals[::step]


# State background colours for plots
STATE_COLORS: Dict[str, str] = {
    "RESET":       "#d9d9d9",
    "STAND":       "#b3d9ff",
    "RL_WALK":     "#b3ffb3",
    "RL_WALK_AMP": "#ffe5b3",
    "RL_MIMIC":    "#f0b3ff",
    "RL_SITUP":    "#ffb3b3",
    "RL_LIEDOWN":  "#e0e0e0",
    "UNKNOWN":     "#f5f5f5",
}

STATE_ZORDER = 0   # background patches drawn behind data
