"""
Main window – ties together FilePanel and the four views.
"""

import tkinter as tk
from tkinter import ttk
from typing import List, Optional

from ui.file_panel import FilePanel
from ui.theme import BG, BG2, FG, FG2, ACCENT, ACCENT_FG, TAB_BG, TAB_ACTIVE, TAB_ACTIVE_FG, TAB_FG, BORDER
from views.joint_view import JointView
from views.overview_view import OverviewView
from views.compare_view import CompareView
from views.robot_view import RobotView


VIEW_NAMES = ["Joint", "Overview", "Compare", "Obs"]
VIEW_CLASSES = [JointView, OverviewView, CompareView, RobotView]


class MainWindow(tk.Frame):
    def __init__(self, root: tk.Tk):
        super().__init__(root, bg=BG)
        root.title("Lumos Log Analyzer")
        root.geometry("1400x860")
        root.minsize(900, 600)
        root.configure(bg=BG)
        self.pack(fill=tk.BOTH, expand=True)
        self._views = {}
        self._current_view_name: Optional[str] = None
        self._build()

    def _build(self):
        # ── Left master panel ──────────────────────────────────────────────
        self._file_panel = FilePanel(
            self, width=220,
            on_data_changed=self._on_data_changed,
        )
        self._file_panel.pack(side=tk.LEFT, fill=tk.Y)

        # thin vertical divider between left panel and right area
        tk.Frame(self, bg=BORDER, width=1).pack(side=tk.LEFT, fill=tk.Y)

        # ── Right side: tab strip + view area ─────────────────────────────
        right = tk.Frame(self, bg=BG)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # ── View switcher buttons ──────────────────────────────────────────
        tab_bar = tk.Frame(right, bg=TAB_BG, height=40)
        tab_bar.pack(side=tk.TOP, fill=tk.X)
        tab_bar.pack_propagate(False)
        # bottom border line
        tk.Frame(right, bg=BORDER, height=1).pack(side=tk.TOP, fill=tk.X)
        self._tab_buttons = {}
        for name in VIEW_NAMES:
            b = tk.Button(
                tab_bar, text=name,
                font=("Helvetica", 10),
                bg=TAB_BG, fg=TAB_FG,
                relief="flat", padx=18,
                highlightthickness=0, bd=0,
                activebackground=TAB_ACTIVE, activeforeground=ACCENT,
                command=lambda n=name: self._switch_view(n),
            )
            b.pack(side=tk.LEFT, ipady=8)
            self._tab_buttons[name] = b

        # ── View container ─────────────────────────────────────────────────
        self._view_container = tk.Frame(right, bg=BG)
        self._view_container.pack(fill=tk.BOTH, expand=True)

        for name, cls in zip(VIEW_NAMES, VIEW_CLASSES):
            view = cls(
                self._view_container,
                get_logs_cb=self._file_panel.get_active_logs,
                get_state_filter_cb=self._file_panel.get_state_filter,
            )
            view.place(relx=0, rely=0, relwidth=1, relheight=1)
            self._views[name] = view

        self._switch_view("Joint")

    def _switch_view(self, name: str):
        if self._current_view_name == name:
            return
        # Lower all, raise target
        for n, v in self._views.items():
            v.lower()
        self._views[name].lift()
        self._current_view_name = name
        # Update tab highlight
        for n, b in self._tab_buttons.items():
            if n == name:
                b.config(bg=TAB_ACTIVE, fg=TAB_ACTIVE_FG, font=("Helvetica", 10, "bold"))
            else:
                b.config(bg=TAB_BG, fg=TAB_FG, font=("Helvetica", 10))

    def _on_data_changed(self):
        """Called whenever files are loaded/unloaded or filter changes."""
        if self._current_view_name:
            view = self._views.get(self._current_view_name)
            if view and hasattr(view, "refresh"):
                self.after(50, view.refresh)
