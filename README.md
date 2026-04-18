# Log Analysis Toolkit

A desktop GUI tool for visualizing and analyzing robot locomotion log files (`.out`, `.INFO`, `.log` format).  
Built with Python 3.10, Tkinter, and Matplotlib — runs fully offline on macOS.

---

## Features

| Feature | Description |
|---|---|
| **Checkbox file loader** | Tick a file to load it instantly; untick to remove it — no extra "Load" button needed |
| **Background parsing** | Log parsing runs in a separate thread so the UI stays responsive |
| **Joint View** | Rows = joints, Columns = field groups; `Position` column overlays actual `q_` (solid) and `target_q_` (dashed orange) on the same axis |
| **Compare View** | Side-by-side comparison of the same joint across multiple log files |
| **Overview View** | Heatmap/summary of all joints in one glance |
| **Robot View** | Animated stick-figure playback of joint angles |
| **State filter** | Filter data by robot state (`STAND`, `RL_WALK`, `RL_MIMIC`, …) with quick-select buttons |
| **macOS light theme** | Forced-light Apple-style color scheme — no dark-mode interference |

---

## Joint Groups

| Group | Joints |
|---|---|
| `L_leg` | left hip pitch/roll/yaw, left knee, left ankle pitch/roll |
| `R_leg` | right hip pitch/roll/yaw, right knee, right ankle pitch/roll |
| `L_ankle` | left ankle pitch, left ankle roll |
| `R_ankle` | right ankle pitch, right ankle roll |
| `torso` | torso |
| `L_arm` | left shoulder pitch/roll/yaw, left elbow |
| `R_arm` | right shoulder pitch/roll/yaw, right elbow |
| `all` | all 21 DOF joints |

---

## Quick Start

### 1. Create the conda environment

```bash
conda env create -f environment.yml
conda activate lumos_log
```

### 2. Run

```bash
cd log_analysis
python app.py
# or
./run.sh
```

---

## Project Structure

```
log_analysis/
├── app.py                  # Entry point
├── environment.yml         # Conda environment spec
├── run.sh                  # One-line launcher
├── core/
│   ├── parser.py           # Glog parser, JOINT_GROUPS, LogData
│   └── analysis.py         # Downsampling, state colors
├── ui/
│   ├── theme.py            # macOS light-theme color constants
│   ├── main_window.py      # Tab bar + layout
│   └── file_panel.py       # Left panel: file browser, state filter
└── views/
    ├── joint_view.py       # Time-series per joint (rows×cols layout)
    ├── overview_view.py    # All-joints heatmap
    ├── compare_view.py     # Multi-file comparison
    └── robot_view.py       # Stick-figure animation
```

---

## Supported Log Fields

| Field | Unit | Description |
|---|---|---|
| `q_` | rad | Actual joint position |
| `target_q_` | rad | Target joint position (command) |
| `qd_` | rad/s | Joint velocity |
| `tau_` | N·m | Joint torque |
| `temp_` | °C | Motor temperature |
| `actions_` | – | RL policy action output |

---

## Requirements

- Python 3.10
- matplotlib ≥ 3.7
- numpy ≥ 1.24
- Tkinter (bundled with conda Python)
