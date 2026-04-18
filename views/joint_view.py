"""
Joint View – time-series plots for selected joints.

Layout:  rows = joints,  columns = field-groups
"Position" column overlays q_ (actual, solid) and target_q_ (dashed) on the
same axis so tracking error is immediately visible.
L/R ankle joints appear as adjacent rows for easy side-by-side comparison.
"""

import tkinter as tk
from typing import List, Optional, Dict

from ui.theme import (BG, BG2 as CTRL_BG, FG, FG2, ACCENT, ACCENT_FG,
                      LIST_BG, SEL_BG, BTN_BG, BTN_FG, BORDER)
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.patches as mpatches

from core.parser import LogData, JOINTS_21, JOINT_GROUPS
from core.analysis import STATE_COLORS, downsample


# ── Field groups ──────────────────────────────────────────────────────────────
# Each entry: (key, display_label, [(field_name, linestyle)])
# Entries with multiple fields share one subplot axis (overlaid).
FIELD_GROUPS = [
    ("pos",      "Position (rad)",   [("q_", "-"),   ("target_q_", "--")]),
    ("velocity", "Velocity (rad/s)", [("qd_",  "-")]),
    ("torque",   "Torque (N·m)",     [("tau_", "-")]),
    ("temp",     "Temp (°C)",        [("temp_","-")]),
    ("actions",  "Actions (–)",      [("actions_", "-")]),
]
FGROUP_MAP  = {g[0]: g for g in FIELD_GROUPS}  # key → (key, label, specs)

# Colors cycling through multiple logs
LOG_COLORS = ["#0071e3", "#e05c00", "#27ae60", "#8e44ad", "#c0392b", "#2980b9"]
# Linestyles for overlaid fields within a group (pos: actual=solid, target=dashed)
FIELD_LS_COLOR = {
    "q_":       ("-",  None),          # color from log
    "target_q_":("--", "#ff6b00"),     # fixed orange-dashed = target
    "qd_":      ("-",  None),
    "tau_":     ("-",  None),
    "temp_":    ("-",  "#c0392b"),
    "actions_": ("-",  "#8e44ad"),
}


class JointView(tk.Frame):
    def __init__(self, parent, get_logs_cb, get_state_filter_cb, **kwargs):
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)
        self._get_logs = get_logs_cb
        self._get_state_filter = get_state_filter_cb
        self._build_ui()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Left control panel ──────────────────────────────────────────────
        ctrl = tk.Frame(self, width=230, bg=CTRL_BG)
        ctrl.pack(side=tk.LEFT, fill=tk.Y)
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text="Field groups", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8, pady=(10, 2))

        self._fg_vars: Dict[str, tk.BooleanVar] = {}
        defaults = {"pos": True, "torque": True, "velocity": False,
                    "temp": False, "actions": False}
        for key, label, specs in FIELD_GROUPS:
            v = tk.BooleanVar(value=defaults.get(key, False))
            self._fg_vars[key] = v
            suffix = "  (q & target)" if key == "pos" else ""
            tk.Checkbutton(ctrl, text=f"{label}{suffix}", variable=v,
                           bg=CTRL_BG, fg=FG, selectcolor=CTRL_BG,
                           activebackground=CTRL_BG, activeforeground=FG,
                           highlightthickness=0, highlightbackground=CTRL_BG,
                           command=self._on_change).pack(anchor="w", padx=16)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill="x", padx=6, pady=6)

        # ── Group quick-select buttons ───────────────────────────────────────
        tk.Label(ctrl, text="Select group", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8)
        btn_frame = tk.Frame(ctrl, bg=CTRL_BG)
        btn_frame.pack(fill="x", padx=8, pady=4)
        for i, g in enumerate(list(JOINT_GROUPS.keys()) + ["all"]):
            tk.Button(btn_frame, text=g, font=("Helvetica", 9), width=9,
                      bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                      highlightthickness=0, highlightbackground=BTN_BG,
                      overrelief="flat",
                      activebackground=SEL_BG, activeforeground=BTN_FG,
                      command=lambda grp=g: self._select_group(grp)
                      ).grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")
        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill="x", padx=6, pady=4)

        # ── Joint multi-select listbox ───────────────────────────────────────
        tk.Label(ctrl, text="Joints", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8)
        lf = tk.Frame(ctrl, bg=CTRL_BG)
        lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        sb = tk.Scrollbar(lf, width=10)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._joint_listbox = tk.Listbox(
            lf, selectmode=tk.MULTIPLE, exportselection=False,
            yscrollcommand=sb.set, height=14, font=("Courier", 9),
            bg=LIST_BG, fg=FG, selectbackground=ACCENT, selectforeground=ACCENT_FG,
            activestyle="none", relief="flat", highlightthickness=0, bd=0,
        )
        for j in JOINTS_21:
            self._joint_listbox.insert(tk.END, j)
        self._joint_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._joint_listbox.yview)
        self._joint_listbox.bind("<<ListboxSelect>>", lambda _e: self._on_change())
        try:
            self._joint_listbox.selection_set(JOINTS_21.index("left_ankle_pitch"))
        except ValueError:
            pass

        tk.Button(ctrl, text="Plot", font=("Helvetica", 10, "bold"),
                  bg=ACCENT, fg=ACCENT_FG, relief="flat", bd=0,
                  highlightthickness=0, highlightbackground=ACCENT,
                  overrelief="flat",
                  activebackground="#005cc5", activeforeground=ACCENT_FG,
                  pady=5, command=self._on_change).pack(fill="x", padx=8, pady=6)

        # ── Right canvas area ────────────────────────────────────────────────
        right = tk.Frame(self, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._toolbar_frame = tk.Frame(right, bg=BG)
        self._toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._canvas_frame = tk.Frame(right, bg=BG)
        self._canvas_frame.pack(fill=tk.BOTH, expand=True)

        self._placeholder = tk.Label(
            self._canvas_frame,
            text="加载日志文件后选择关节并点击 Plot",
            font=("Helvetica", 14), fg=FG2, bg=BG,
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self._canvas: Optional[FigureCanvasTkAgg] = None

    # ── helpers ───────────────────────────────────────────────────────────────

    def _select_group(self, group: str):
        self._joint_listbox.selection_clear(0, tk.END)
        targets = JOINTS_21 if group == "all" else JOINT_GROUPS.get(group, [])
        for jname in targets:
            if jname in JOINTS_21:
                self._joint_listbox.selection_set(JOINTS_21.index(jname))
        self._on_change()

    def _selected_joints(self) -> List[str]:
        return [JOINTS_21[i] for i in self._joint_listbox.curselection()]

    def _selected_fgroups(self):
        return [(k, l, s) for k, l, s in FIELD_GROUPS if self._fg_vars[k].get()]

    def _on_change(self):
        self.after_idle(self.plot)

    # ── plotting ──────────────────────────────────────────────────────────────

    def plot(self):
        logs: List[LogData] = self._get_logs()
        if not logs:
            return
        joints  = self._selected_joints()
        fgroups = self._selected_fgroups()
        state_filter = self._get_state_filter()
        if not joints or not fgroups:
            return

        n_rows = len(joints)
        n_cols = len(fgroups)
        fig = Figure(
            figsize=(max(6, 4.2 * n_cols), max(4, 2.6 * n_rows)), dpi=96)
        fig.patch.set_facecolor("#ffffff")
        fig.subplots_adjust(hspace=0.55, wspace=0.38,
                            left=0.07, right=0.97, top=0.93, bottom=0.06)

        for ri, jname in enumerate(joints):
            for ci, (gkey, glabel, gspecs) in enumerate(fgroups):
                ax = fig.add_subplot(n_rows, n_cols, ri * n_cols + ci + 1)
                ax.set_facecolor("#fafafa")
                # title: joint name on row 0 only (avoids repetition)
                title = f"{jname}" if ci == 0 else ""
                if title:
                    ax.set_ylabel(jname, fontsize=7, labelpad=2)
                ax.set_title(glabel, fontsize=7, pad=3)
                ax.set_xlabel("t (s)", fontsize=6)
                ax.tick_params(labelsize=6)

                legend_items = []
                for li, log in enumerate(logs):
                    lcolor = LOG_COLORS[li % len(LOG_COLORS)]
                    sf = state_filter if state_filter else None
                    for field, _ in gspecs:
                        ts, vals = log.get_series(field, jname, sf)
                        if not ts:
                            continue
                        ts, vals = downsample(ts, vals)
                        ls, fcolor = FIELD_LS_COLOR.get(field, ("-", None))
                        color = fcolor if fcolor else lcolor
                        lbl = (f"{log.filename[:12]}" if len(logs) == 1
                               else f"{log.filename[:10]}")
                        if len(gspecs) > 1:
                            lbl += f"/{field.rstrip('_')}"
                        line, = ax.plot(ts, vals, linestyle=ls, linewidth=0.9,
                                        color=color, label=lbl)
                        legend_items.append(line)
                    _shade_states(ax, log, state_filter)

                if legend_items:
                    ax.legend(handles=legend_items, fontsize=5,
                              loc="best", framealpha=0.7,
                              handlelength=1.5, labelspacing=0.3)

        # State color legend at figure level
        state_patches = [mpatches.Patch(color=c, label=s, alpha=0.5)
                         for s, c in STATE_COLORS.items()]
        fig.legend(handles=state_patches, loc="upper right", fontsize=6,
                   title="State", ncol=4, bbox_to_anchor=(0.99, 0.99))

        self._render(fig)

    def _render(self, fig: Figure):
        self._placeholder.place_forget()
        if self._canvas:
            self._canvas.get_tk_widget().destroy()
        for w in self._toolbar_frame.winfo_children():
            w.destroy()
        self._canvas = FigureCanvasTkAgg(fig, master=self._canvas_frame)
        self._canvas.draw()
        widget = self._canvas.get_tk_widget()
        widget.configure(bg=BG)
        widget.pack(fill=tk.BOTH, expand=True)
        tb = NavigationToolbar2Tk(self._canvas, self._toolbar_frame)
        tb.configure(bg=BG)
        for child in tb.winfo_children():
            try:
                child.configure(bg=BG, highlightthickness=0,
                                relief="flat", bd=0)
            except Exception:
                pass
        tb.update()

    def refresh(self):
        self.plot()


# ── module-level helper ───────────────────────────────────────────────────────

def _shade_states(ax, log: LogData,
                  state_filter: Optional[List[str]] = None):
    for seg in log.state_segments:
        if state_filter and seg.state not in state_filter:
            continue
        color = STATE_COLORS.get(seg.state, "#eeeeee")
        ax.axvspan(seg.start_ts, seg.end_ts, color=color, alpha=0.18, zorder=0)
