"""
Robot View – body-level telemetry: rpy, omega, cmd_, projected_gravity.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Dict

from ui.theme import BG, BG2 as CTRL_BG, FG, FG2, ACCENT, ACCENT_FG, LIST_BG, SEL_BG, BTN_BG, BTN_FG, BORDER
import matplotlib.patches as mpatches
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from core.parser import LogData
from core.analysis import STATE_COLORS, downsample
from views.joint_view import _shade_states


PANELS = [
    ("rpy",   "roll",  "roll",    "rad"),
    ("rpy",   "pitch", "pitch",   "rad"),
    ("rpy",   "yaw",   "yaw",     "rad"),
    ("omega", "0",     "omega_x", "rad/s"),
    ("omega", "1",     "omega_y", "rad/s"),
    ("omega", "2",     "omega_z", "rad/s"),
    ("cmd_",  "0",     "cmd_vx",  "m/s"),
    ("cmd_",  "1",     "cmd_vy",  "m/s"),
    ("cmd_",  "2",     "cmd_yaw", "rad/s"),
    ("projected_gravity", "0", "grav_x", "–"),
    ("projected_gravity", "1", "grav_y", "–"),
    ("projected_gravity", "2", "grav_z", "–"),
]
LINE_COLORS = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b"]


class RobotView(tk.Frame):
    def __init__(self, parent, get_logs_cb, get_state_filter_cb, **kwargs):
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)
        self._get_logs = get_logs_cb
        self._get_state_filter = get_state_filter_cb
        self._panel_vars: Dict[int, tk.BooleanVar] = {}
        self._build_ui()

    def _build_ui(self):
        ctrl = tk.Frame(self, width=200, bg=CTRL_BG)
        ctrl.pack(side=tk.LEFT, fill=tk.Y)
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text="Channels", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8, pady=(10, 2))

        defaults_on = {"roll", "pitch", "yaw", "cmd_vx", "cmd_vy", "grav_z"}
        for i, (field, comp, label, unit) in enumerate(PANELS):
            v = tk.BooleanVar(value=(label in defaults_on))
            self._panel_vars[i] = v
            tk.Checkbutton(ctrl, text=f"{label}  ({unit})", variable=v,
                           bg=CTRL_BG, fg=FG, selectcolor=CTRL_BG,
                           activebackground=CTRL_BG, activeforeground=FG,
                           command=self._on_change).pack(anchor="w", padx=14)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill="x", padx=6, pady=6)

        def select_group(keys):
            for i, (_, _, lb, _) in enumerate(PANELS):
                self._panel_vars[i].set(lb in keys)
            self._on_change()

        groups = [
            ("RPY",   {"roll", "pitch", "yaw"}),
            ("Omega", {"omega_x", "omega_y", "omega_z"}),
            ("Cmd",   {"cmd_vx", "cmd_vy", "cmd_yaw"}),
            ("Grav",  {"grav_x", "grav_y", "grav_z"}),
            ("All",   {p[2] for p in PANELS}),
        ]
        for gname, gset in groups:
            tk.Button(ctrl, text=gname, font=("Helvetica", 9),
                      bg=BTN_BG, fg=BTN_FG, relief="flat",
                      highlightthickness=0, activebackground=SEL_BG,
                      command=lambda s=gset: select_group(s)).pack(fill="x", padx=8, pady=2)

        tk.Button(ctrl, text="Plot", font=("Helvetica", 10, "bold"),
                  bg=ACCENT, fg=ACCENT_FG, relief="flat",
                  highlightthickness=0,
                  activebackground="#005cc5", activeforeground=ACCENT_FG,
                  pady=5, command=self._on_change).pack(fill="x", padx=8, pady=8)

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
        logs: List[LogData] = self._get_logs()
        if not logs:
            return
        state_filter = self._get_state_filter()
        selected = [(f, c, lb, u) for i, (f, c, lb, u) in enumerate(PANELS)
                    if self._panel_vars[i].get()]
        if not selected:
            return

        n = len(selected)
        cols = min(n, 3)
        rows = (n + cols - 1) // cols
        fig = Figure(figsize=(max(6, 4.5 * cols), max(3, 2.6 * rows)), dpi=96)
        fig.patch.set_facecolor("#ffffff")
        fig.subplots_adjust(hspace=0.55, wspace=0.38,
                            left=0.08, right=0.97, top=0.92, bottom=0.08)

        for pi, (field, comp, label, unit) in enumerate(selected):
            ax = fig.add_subplot(rows, cols, pi + 1)
            ax.set_facecolor("#fafafa")
            for li, log in enumerate(logs):
                sf = state_filter if state_filter else None
                ts, vals = log.get_series(field, comp, sf)
                if not ts:
                    continue
                ts, vals = downsample(ts, vals)
                ax.plot(ts, vals, color=LINE_COLORS[li % len(LINE_COLORS)],
                        linewidth=0.9, label=log.filename[:16], alpha=0.9)
                _shade_states(ax, log, sf)
            ax.set_title(label, fontsize=9)
            ax.set_xlabel("t (s)", fontsize=7)
            ax.set_ylabel(unit, fontsize=7)
            ax.tick_params(labelsize=7)
            if len(logs) > 1:
                ax.legend(fontsize=6)

        patches = [mpatches.Patch(color=c, label=s, alpha=0.5)
                   for s, c in STATE_COLORS.items()]
        fig.legend(handles=patches, loc="upper right", fontsize=7,
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
                child.configure(bg=BG, highlightthickness=0, relief="flat", bd=0)
            except Exception:
                pass
        tb.update()

    def refresh(self):
        self.plot()
