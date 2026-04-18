"""
Log parser for Lumos robot log files.
Parses Glog-format .out / .INFO files and extracts all per-frame fields.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import numpy as np

# ─────────────────────────────────────────────
#  Joint layout tables (index → short name)
# ─────────────────────────────────────────────

# Full 21-DOF layout used by RL_WALK_AMP / RL_MIMIC / RL_WALK (21-dim)
JOINTS_21 = [
    "left_hip_pitch",  "left_hip_roll",  "left_hip_yaw",
    "left_knee",
    "left_ankle_pitch","left_ankle_roll",
    "right_hip_pitch", "right_hip_roll", "right_hip_yaw",
    "right_knee",
    "right_ankle_pitch","right_ankle_roll",
    "torso",
    "left_shoulder_pitch","left_shoulder_roll","left_shoulder_yaw","left_elbow",
    "right_shoulder_pitch","right_shoulder_roll","right_shoulder_yaw","right_elbow",
]

# STAND uses 27 DOF (torso pitch/roll added, extra ankle joints, etc.)
# We store them generically as j0…j26
JOINTS_27 = [f"j{i}" for i in range(27)]

# RL_WALK uses 12 DOF (legs only)
JOINTS_12 = [
    "left_hip_pitch",  "left_hip_roll",  "left_hip_yaw",
    "left_knee",
    "left_ankle_pitch","left_ankle_roll",
    "right_hip_pitch", "right_hip_roll", "right_hip_yaw",
    "right_knee",
    "right_ankle_pitch","right_ankle_roll",
]

# Body segment grouping (for 21-DOF joints)
JOINT_GROUPS = {
    "L_leg":    ["left_hip_pitch","left_hip_roll","left_hip_yaw","left_knee","left_ankle_pitch","left_ankle_roll"],
    "R_leg":    ["right_hip_pitch","right_hip_roll","right_hip_yaw","right_knee","right_ankle_pitch","right_ankle_roll"],
    "L_ankle":  ["left_ankle_pitch","left_ankle_roll"],
    "R_ankle":  ["right_ankle_pitch","right_ankle_roll"],
    "torso":    ["torso"],
    "L_arm":    ["left_shoulder_pitch","left_shoulder_roll","left_shoulder_yaw","left_elbow"],
    "R_arm":    ["right_shoulder_pitch","right_shoulder_roll","right_shoulder_yaw","right_elbow"],
}

# State → joint table
STATE_JOINTS: Dict[str, List[str]] = {
    "STAND":       JOINTS_27,
    "RL_WALK":     JOINTS_12,
    "RL_WALK_AMP": JOINTS_21,
    "RL_MIMIC":    JOINTS_21,
    "RL_SITUP":    [f"j{i}" for i in range(23)],
    "RL_LIEDOWN":  [f"j{i}" for i in range(26)],
    "RESET":       [],
}

# Per-frame vector fields
VECTOR_FIELDS = ["q_", "qd_", "tau_", "temp_", "target_q_", "actions_"]
# Per-frame scalar-group fields (fixed dimension)
SCALAR_FIELDS = {
    "rpy":              3,
    "omega":            3,
    "quat":             4,
    "projected_gravity":3,
    "cmd_":             3,
}

# ─────────────────────────────────────────────
#  Data structures
# ─────────────────────────────────────────────

@dataclass
class Frame:
    timestamp: float          # seconds since start of file
    time_str:  str            # original HH:MM:SS.us string
    state:     str            # active state name at this frame
    # 21-dim (or N-dim) joint vectors – None if not present in this state
    q_:         Optional[List[float]] = None
    qd_:        Optional[List[float]] = None
    tau_:       Optional[List[float]] = None
    temp_:      Optional[List[float]] = None
    target_q_:  Optional[List[float]] = None
    actions_:   Optional[List[float]] = None
    # 3/4-dim body state
    rpy:              Optional[List[float]] = None  # [roll, pitch, yaw]
    omega:            Optional[List[float]] = None
    quat:             Optional[List[float]] = None
    projected_gravity:Optional[List[float]] = None
    cmd_:             Optional[List[float]] = None


@dataclass
class StateSegment:
    state: str
    start_ts: float
    end_ts:   float
    start_idx: int   # frame index
    end_idx:   int


@dataclass
class LogData:
    filepath:        str
    filename:        str
    frames:          List[Frame]
    state_segments:  List[StateSegment]
    errors:          List[Tuple[float, str]]
    warnings:        List[Tuple[float, str]]
    transitions:     List[Tuple[float, str, str]]  # (ts, from, to)

    # ── convenience helpers ─────────────────

    @property
    def duration(self) -> float:
        if not self.frames:
            return 0.0
        return self.frames[-1].timestamp - self.frames[0].timestamp

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def states_present(self) -> List[str]:
        seen = []
        for s in self.state_segments:
            if s.state not in seen:
                seen.append(s.state)
        return seen

    def get_series(self, field: str, joint_name: Optional[str] = None,
                   state_filter: Optional[List[str]] = None
                   ) -> Tuple[List[float], List[float]]:
        """
        Return (timestamps, values) for a given field.

        For vector fields (q_, tau_, …) supply joint_name (short name from JOINTS_21).
        For scalar-group fields (rpy, omega, …) supply joint_name as the component
        index string: '0','1','2' or the component name 'roll','pitch','yaw' for rpy.
        """
        rpy_components = {"roll": 0, "pitch": 1, "yaw": 2}
        omega_components = {"wx": 0, "wy": 1, "wz": 2}

        ts_list, val_list = [], []
        for fr in self.frames:
            if state_filter and fr.state not in state_filter:
                continue
            vec = getattr(fr, field, None)
            if vec is None:
                continue
            if joint_name is not None:
                # resolve index
                if field in VECTOR_FIELDS:
                    jmap = STATE_JOINTS.get(fr.state, JOINTS_21)
                    if joint_name in jmap:
                        idx = jmap.index(joint_name)
                    else:
                        continue
                elif field == "rpy":
                    idx = rpy_components.get(joint_name, None)
                    if idx is None:
                        try: idx = int(joint_name)
                        except ValueError: continue
                elif field == "omega":
                    idx = omega_components.get(joint_name, None)
                    if idx is None:
                        try: idx = int(joint_name)
                        except ValueError: continue
                else:
                    try: idx = int(joint_name)
                    except ValueError: continue
                if idx >= len(vec):
                    continue
                val_list.append(vec[idx])
            else:
                val_list.append(vec)  # return whole vector
            ts_list.append(fr.timestamp)
        return ts_list, val_list


# ─────────────────────────────────────────────
#  Parser
# ─────────────────────────────────────────────

# Glog line:  [IWEF]mmdd HH:MM:SS.uuuuuu  tid  file:line] msg
_GLOG_RE = re.compile(
    r'^([IWEF])(\d{4})\s+(\d{2}:\d{2}:\d{2}\.\d+)\s+\d+\s+\S+\]\s*(.*)'
)

# State transition patterns
_TRANS_RE = re.compile(
    r'(?:state change|transfer from)\s*[:\s]*'
    r'([A-Z_]+)\s*(?:->|to)\s*([A-Z_]+)',
    re.IGNORECASE
)

# Vector field  "tau_: 1.2 -3.4 ..."
_VEC_RE = re.compile(r'^(\w+):\s+([-\d. eE+]+)$')

# Scalar group  "rpy :0.02 0.01 -0.04"  or  "rpy: 0.02 ..."
_SCALAR_RE = re.compile(r'^(rpy|omega|quat|projected_gravity|cmd_)\s*:?\s*([-\d. eE+]+)$', re.IGNORECASE)


def _parse_floats(s: str) -> List[float]:
    return [float(x) for x in s.split()]


def _time_to_seconds(t: str) -> float:
    h, m, rest = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(rest)


class LogParser:
    def parse_file(self, filepath: str) -> LogData:
        path = Path(filepath)
        frames: List[Frame] = []
        errors: List[Tuple[float, str]] = []
        warnings: List[Tuple[float, str]] = []
        transitions: List[Tuple[float, str, str]] = []

        # rolling state
        current_state = "UNKNOWN"
        base_ts: Optional[float] = None

        # accumulator: collect all fields for one "frame group"
        # A frame group = all lines sharing the same timestamp cluster (~same ms)
        # We detect a new frame when q_ reappears (it's usually the first vector per tick)
        acc: Dict[str, object] = {}
        acc_ts: Optional[float] = None
        acc_tsstr: str = ""
        acc_state: str = "UNKNOWN"

        def _flush_frame():
            nonlocal acc, acc_ts, acc_tsstr, acc_state
            if acc_ts is None:
                return
            fr = Frame(
                timestamp=acc_ts,
                time_str=acc_tsstr,
                state=acc_state,
            )
            for f in VECTOR_FIELDS:
                if f in acc:
                    setattr(fr, f, acc[f])
            for f in SCALAR_FIELDS:
                if f in acc:
                    setattr(fr, f, acc[f])
            frames.append(fr)
            acc = {}
            acc_ts = None

        try:
            with open(filepath, "r", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.rstrip("\n")
                    m = _GLOG_RE.match(line)
                    if not m:
                        continue
                    level, _date, time_str, msg = m.groups()
                    ts = _time_to_seconds(time_str)
                    if base_ts is None:
                        base_ts = ts
                    ts -= base_ts

                    # ── state transitions ──
                    tm = _TRANS_RE.search(msg)
                    if tm:
                        from_s, to_s = tm.group(1).upper(), tm.group(2).upper()
                        transitions.append((ts, from_s, to_s))
                        current_state = to_s

                    # ── errors / warnings ──
                    if level == "E":
                        errors.append((ts, msg))
                    elif level == "W":
                        # skip noisy onEnter/onExit lines
                        if "onEnter" not in msg and "onExit" not in msg:
                            warnings.append((ts, msg))

                    # ── vector fields ──
                    # Match lines like "q_: 1.2 3.4 ..." or "tau_: ..."
                    msg_stripped = msg.strip()

                    # Check scalar groups first (rpy, omega, etc.)
                    sm = _SCALAR_RE.match(msg_stripped)
                    if sm:
                        key_raw = sm.group(1).lower()
                        # normalise "rpy" / "projected_gravity"
                        key = key_raw if key_raw in SCALAR_FIELDS else key_raw + "_"
                        try:
                            vals = _parse_floats(sm.group(2))
                            if acc_ts is None:
                                acc_ts = ts
                                acc_tsstr = time_str
                                acc_state = current_state
                            # Normalise "projected_gravity" key
                            if key_raw == "projected_gravity":
                                acc["projected_gravity"] = vals
                            elif key_raw in ("rpy",):
                                acc["rpy"] = vals
                            elif key_raw in ("omega",):
                                acc["omega"] = vals
                            elif key_raw in ("quat",):
                                acc["quat"] = vals
                            elif key_raw in ("cmd_",):
                                acc["cmd_"] = vals
                        except ValueError:
                            pass
                        continue

                    # Vector fields: "q_: ...", "tau_: ...", etc.
                    vm = _VEC_RE.match(msg_stripped)
                    if vm:
                        key = vm.group(1)
                        if key in VECTOR_FIELDS:
                            try:
                                vals = _parse_floats(vm.group(2))
                            except ValueError:
                                continue
                            # q_ signals a new frame boundary
                            if key == "q_":
                                _flush_frame()
                                acc_ts = ts
                                acc_tsstr = time_str
                                acc_state = current_state
                            if acc_ts is None:
                                acc_ts = ts
                                acc_tsstr = time_str
                                acc_state = current_state
                            acc[key] = vals

            _flush_frame()

        except Exception as e:
            errors.append((0.0, f"Parse error: {e}"))

        # Build state segments
        segments = _build_segments(frames, transitions)

        return LogData(
            filepath=str(path),
            filename=path.name,
            frames=frames,
            state_segments=segments,
            errors=errors,
            warnings=warnings,
            transitions=transitions,
        )

    def parse_multiple(self, filepaths: List[str]) -> List[LogData]:
        return [self.parse_file(fp) for fp in filepaths]


def _build_segments(frames: List[Frame], transitions: List[Tuple[float, str, str]]) -> List[StateSegment]:
    if not frames:
        return []
    segments: List[StateSegment] = []
    if not transitions:
        segments.append(StateSegment(
            state=frames[0].state if frames else "UNKNOWN",
            start_ts=frames[0].timestamp,
            end_ts=frames[-1].timestamp,
            start_idx=0,
            end_idx=len(frames) - 1,
        ))
        return segments

    # Walk transitions and find frame indices
    trans_idx = 0
    seg_start_idx = 0
    seg_start_ts = frames[0].timestamp
    seg_state = frames[0].state

    # Find the frame index that is >= a given timestamp
    ts_array = [f.timestamp for f in frames]

    def find_idx(ts: float) -> int:
        lo, hi = 0, len(ts_array) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if ts_array[mid] < ts:
                lo = mid + 1
            else:
                hi = mid
        return lo

    # Collect unique boundary timestamps from transitions
    boundaries: List[Tuple[float, str]] = []  # (ts, new_state)
    for ts, _from, to in transitions:
        boundaries.append((ts, to))

    for (bts, bstate) in boundaries:
        end_idx = find_idx(bts) - 1
        if end_idx < seg_start_idx:
            seg_state = bstate
            seg_start_idx = find_idx(bts)
            seg_start_ts = bts
            continue
        if end_idx >= seg_start_idx:
            segments.append(StateSegment(
                state=seg_state,
                start_ts=seg_start_ts,
                end_ts=ts_array[end_idx],
                start_idx=seg_start_idx,
                end_idx=end_idx,
            ))
        seg_state = bstate
        seg_start_idx = find_idx(bts)
        seg_start_ts = bts

    # Final segment
    segments.append(StateSegment(
        state=seg_state,
        start_ts=seg_start_ts,
        end_ts=frames[-1].timestamp,
        start_idx=seg_start_idx,
        end_idx=len(frames) - 1,
    ))
    return segments
