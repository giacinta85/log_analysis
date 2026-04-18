"""
Compare View – overlay multiple log files on the same axes.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

from ui.theme import BG, BG2 as CTRL_BG, FG, FG2, ACCENT, ACCENT_FG, LIST_BG, SEL_BG, BTN_BG, BTN_FG, BORDER
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from core.parser import LogData, JOINTS_21, JOINT_GROUPS
from core.analysis import STATE_COLORS, downsample
from views.joint_view import _shade_states


COMPARE_FIELDS = ["tau_", "q_", "qd_", "temp_", "target_q_", "actions_",
                  "rpy.roll", "rpy.pitch", "rpy.yaw",
                  "omega.0", "omega.1", "omega.2",
                  "cmd_.0", "cmd_.1", "cmd_.2"]

FIELD_UNITS_C = {
    "tau_": "N·m", "q_": "rad", "qd_": "rad/s", "temp_": "°C",
    "target_q_": "rad", "actions_": "–",
    "rpy.roll": "rad", "rpy.pitch": "rad", "rpy.yaw": "rad",
    "omega.0": "rad/s", "omega.1": "rad/s", "omega.2": "rad/s",
    "cmd_.0": "m/s", "cmd_.1": "m/s", "cmd_.2": "rad/s",
}
LINE_COLORS = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd",
               "#8c564b","#e377c2","#7f7f7f"]


class CompareView(tk.Frame):
    def __init__(self, parent, get_logs_cb, get_state_filter_cb, **kwargs):
        kwargs.setdefault("bg", BG)
        super().__init__(parent, **kwargs)
        self._get_logs = get_logs_cb
        self._get_state_filter = get_state_filter_cb
        self._build_ui()

    def _build_ui(self):
        ctrl = tk.Frame(self, width=220, bg=CTRL_BG)
        ctrl.pack(side=tk.LEFT, fill=tk.Y)
        ctrl.pack_propagate(False)

        tk.Label(ctrl, text="Field", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8, pady=(10, 2))
        self._field_var = tk.StringVar(value="tau_")
        self._field_combo = ttk.Combobox(ctrl, textvariable=self._field_var,
                                         values=COMPARE_FIELDS, state="readonly", width=18)
        self._field_combo.pack(padx=8, pady=4, fill="x")
        self._field_combo.bind("<<ComboboxSelected>>", lambda _: self._on_change())

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill="x", padx=6, pady=4)

        tk.Label(ctrl, text="Select group", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8)
        bf = tk.Frame(ctrl, bg=CTRL_BG)
        bf.pack(fill="x", padx=8, pady=4)
        for i, g in enumerate(list(JOINT_GROUPS.keys()) + ["all"]):
            tk.Button(bf, text=g, font=("Helvetica", 9), width=8,
                      bg=BTN_BG, fg=BTN_FG, relief="flat", bd=0,
                      highlightthickness=0, activebackground=SEL_BG,
                      activeforeground=BTN_FG,
                      command=lambda grp=g: self._select_group(grp)
                      ).grid(row=i // 2, column=i % 2, padx=2, pady=2, sticky="ew")
        bf.columnconfigure(0, weight=1)
        bf.columnconfigure(1, weight=1)

        tk.Frame(ctrl, bg=BORDER, height=1).pack(fill="x", padx=6, pady=4)

        tk.Label(ctrl, text="Joints", font=("Helvetica", 11, "bold"),
                 bg=CTRL_BG, fg=FG).pack(anchor="w", padx=8)
        lf = tk.Frame(ctrl, bg=CTRL_BG)
        lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 4))
        sb = tk.Scrollbar(lf, width=10)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._joint_lb = tk.Listbox(
            lf, selectmode=tk.MULTIPLE, exportselection=False,
            yscrollcommand=sb.set, height=12, font=("Courier", 9),
            bg=LIST_BG, fg=FG, selectbackground=ACCENT, selectforeground=ACCENT_FG,
            activestyle="none", relief="flat", highlightthickness=0, bd=0,
        )
        for j in JOINTS_21:
            self._joint_lb.insert(tk.END, j)
        self._joint_lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.config(command=self._joint_lb.yview)
        self._joint_lb.bind("<<ListboxSelect>>", lambda _e: self._on_change())
        try:
            self._joint_lb.selection_set(JOINTS_21.index("left_knee"))
        except ValueError:
            pass

        tk.Button(ctrl, text="Plot", font=("Helvetica", 10, "bold"),
                  bg=ACCENT, fg=ACCENT_FG, relief="flat",
                  highlightthickness=0,
                  activebackground="#005cc5", activeforeground=ACCENT_FG,
                  pady=5, command=self._on_change).pack(fill="x", padx=8, pady=6)

        right = tk.Frame(self, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._toolbar_frame = tk.Frame(right, bg=BG)
        self._toolbar_frame.pack(side=tk.BOTTOM, fill=tk.X)

        self._canvas_frame = tk.Frame(right, bg=BG)
        self._canvas_frame.pack(fill=tk.BOTH, expand=True)

        self._placeholder = tk.Label(
            self._canvas_frame,
            text="Load log files, then click  Plot",
            font=("Helvetica", 14), fg=FG2, bg=BG,
        )
        self._placeholder.place(relx=0.5, rely=0.5, anchor="center")

        self._canvas: Optional[FigureCanvasTkAgg] = None

    def _select_group(self, group: str):
        self._joint_lb.selection_clear(0, tk.END)
        targets = JOINTS_21 if group == "all" else JOINT_GROUPS.get(group, [])
        for jname in targets:
            if jname in JOINTS_21:
                self._joint_lb.selection_set(JOINTS_21.index(jname))
        self._on_change()

    def _selected_joints(self):
        return [JOINTS_21[i] for i in self._joint_lb.curselection()]

    def _on_change(self):
        self.after_idle(self.plot)

    def plot(self):
        logs: List[LogData] = self._get_logs()
        if not logs:
            return
        field_key = self._field_var.get()
        joints = self._selected_joints()
        state_filter = self._get_state_filter()
        is_scalar = "." in field_key
        if is_scalar:
            base_field, component = field_key.split(".", 1)
        else:
            base_field, component = field_key, None
        if not is_scalar and not joints:
            return

        subplot_items = [field_key] if is_scalar else joints
        n = len(subplot_items)
        cols = min(n, 3)
        rows = (n + cols - 1) // cols
        fig = Figure(figsize=(max(6, 4.5 * cols), max(3, 2.8 * rows)), dpi=96)
        fig.patch.set_facecolor("#ffffff")
        fig.subplots_adjust(hspace=0.45, wspace=0.35,
                            left=0.08, right=0.97, top=0.92, bottom=0.08)

        for pi, item in enumerate(subplot_items):
            ax = fig.add_subplot(rows, cols, pi + 1)
            ax.set_facecolor("#fafafa")
            for li, log in enumerate(logs):
                sf = state_filter if state_filter else None
                ts, vals = log.get_series(base_field, component if is_scalar else item, sf)
                if not ts:
                    continue
                ts, vals = downsample(ts, vals)
                ax.plot(ts, vals, color=LINE_COLORS[li % len(LINE_COLORS)],
                        linewidth=0.9, label=log.filename[:18], alpha=0.85)
                _shade_states(ax, log, sf)
            ax.set_title(item, fontsize=8)
            ax.set_xlabel("t (s)", fontsize=7)
            ax.set_ylabel(FIELD_UNITS_C.get(field_key, ""), fontsize=7)
            ax.tick_params(labelsize=7)
            if len(logs) > 1:
                ax.legend(fontsize=6)

        fig.suptitle(f"Compare: {field_key}", fontsize=10)
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
