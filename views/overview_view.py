"""
Overview View – per-joint statistical bar charts grouped by body segment.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

from ui.theme import BG, BG2 as CTRL_BG, FG, FG2, ACCENT, ACCENT_FG, LIST_BG, SEL_BG, BTN_BG, BTN_FG, BORDER
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from core.parser import LogData, JOINTS_21, JOINT_GROUPS, VECTOR_FIELDS
from core.analysis import compute_joint_stats, STATE_COLORS


STAT_OPTIONS  = ["mean", "max", "min", "std"]
FIELD_OPTIONS = ["tau_", "temp_", "q_", "qd_", "target_q_"]
FIELD_UNITS   = {"tau_": "N·m", "temp_": "°C", "q_": "rad", "qd_": "rad/s", "target_q_": "rad"}
GROUP_COLORS  = {"L_leg": "#4a90d9", "R_leg": "#50c878", "torso": "#888888",
                 "L_arm": "#ff8c42", "R_arm": "#e04040"}


class OverviewView(tk.Frame):
    def __init__(self, parent, get_logs_cb, get_state_filter_cb, **kwargs):
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)
        self._get_logs = get_logs_cb
        self._get_state_filter = get_state_filter_cb
        self._build_ui()

    def _build_ui(self):
        ctrl = tk.Frame(self, width=200, bg=CTRL_BG)
        ctrl.pack(side=tk.LEFT, fill=tk.Y)
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text="Field", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8, pady=(10, 2))
        self._field_var = tk.StringVar(value="tau_")
        for f in FIELD_OPTIONS:
            tk.Radiobutton(ctrl, text=f"{f}  ({FIELD_UNITS.get(f,'')})",
                           variable=self._field_var, value=f,
                           bg=CTRL_BG, fg=FG, selectcolor=CTRL_BG,
                           activebackground=CTRL_BG, activeforeground=FG,
                           command=self._on_change).pack(anchor="w", padx=16)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill="x", padx=6, pady=6)

        tk.Label(ctrl, text="Statistic", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8)
        self._stat_var = tk.StringVar(value="mean")
        for s in STAT_OPTIONS:
            tk.Radiobutton(ctrl, text=s, variable=self._stat_var, value=s,
                           bg=CTRL_BG, fg=FG, selectcolor=CTRL_BG,
                           activebackground=CTRL_BG, activeforeground=FG,
                           command=self._on_change).pack(anchor="w", padx=16)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill="x", padx=6, pady=6)

        self._errbar_var = tk.BooleanVar(value=True)
        tk.Checkbutton(ctrl, text="Show std bars", variable=self._errbar_var,
                       bg=CTRL_BG, fg=FG, selectcolor=CTRL_BG,
                       activebackground=CTRL_BG, activeforeground=FG,
                       command=self._on_change).pack(anchor="w", padx=16)

        tk.Button(ctrl, text="Plot", font=("Helvetica", 10, "bold"),
                  bg=ACCENT, fg=ACCENT_FG, relief="flat", bd=0,
                  highlightthickness=0, highlightbackground=ACCENT,
                  overrelief="flat",
                  activebackground="#005cc5", activeforeground=ACCENT_FG,
                  pady=5, command=self._on_change).pack(fill="x", padx=8, pady=10)

        right = tk.Frame(self, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._toolbar_frame = tk.Frame(right, bg=BG)
        self._toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._canvas_frame = tk.Frame(right, bg=BG)
        self._canvas_frame.pack(fill=tk.BOTH, expand=True)

        self._placeholder = tk.Label(
            self._canvas_frame,
            text="Load a log file, then click  Plot",
            font=("Helvetica", 14), fg=FG2, bg=BG,
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self._canvas: Optional[FigureCanvasTkAgg] = None

    def _on_change(self):
        self.after_idle(self.plot)

    def plot(self):
        logs = self._get_logs()
        if not logs:
            return
        field = self._field_var.get()
        stat  = self._stat_var.get()
        show_err = self._errbar_var.get()
        state_filter = self._get_state_filter()

        n_groups = len(JOINT_GROUPS)
        fig = Figure(figsize=(14, 5), dpi=96)
        fig.patch.set_facecolor("#ffffff")
        fig.subplots_adjust(hspace=0.5, wspace=0.4, left=0.06, right=0.97, top=0.88, bottom=0.22)

        for gi, (gname, gjoints) in enumerate(JOINT_GROUPS.items()):
            ax = fig.add_subplot(1, n_groups, gi + 1)
            ax.set_facecolor("#fafafa")
            color = GROUP_COLORS.get(gname, "#888888")
            x = np.arange(len(gjoints))
            width = 0.8 / max(len(logs), 1)
            for li, log in enumerate(logs):
                sf = state_filter if state_filter else None
                stats_dict = {s.name: s for s in compute_joint_stats(log, field, sf)}
                vals, errs = [], []
                for jn in gjoints:
                    s = stats_dict.get(jn)
                    if s is None or s.count == 0:
                        vals.append(0); errs.append(0)
                    else:
                        vals.append(getattr(s, {"mean":"mean","max":"max_val","min":"min_val","std":"std"}[stat]))
                        errs.append(s.std)
                offset = (li - (len(logs) - 1) / 2) * width
                ax.bar(x + offset, vals, width=width,
                       yerr=errs if (show_err and stat == "mean") else None,
                       capsize=3, color=color,
                       alpha=0.7 + 0.3 * (li / max(len(logs), 1)),
                       label=log.filename[:18])
            short = [j.replace("_pitch","_p").replace("_roll","_r").replace("_yaw","_y")
                      .replace("_ankle","_ank").replace("left_","L_").replace("right_","R_")
                      for j in gjoints]
            ax.set_xticks(x)
            ax.set_xticklabels(short, rotation=35, ha="right", fontsize=7)
            ax.set_title(f"{gname}  {field} {stat}", fontsize=9)
            ax.set_ylabel(FIELD_UNITS.get(field, ""), fontsize=8)
            ax.tick_params(labelsize=7)
            ax.axhline(0, color="#aaaaaa", linewidth=0.5, linestyle="--")
            if len(logs) > 1:
                ax.legend(fontsize=6)

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
                child.configure(bg=BG, highlightthickness=0, relief="flat", bd=0)
            except Exception:
                pass
        tb.update()

    def refresh(self):
        self.plot()
