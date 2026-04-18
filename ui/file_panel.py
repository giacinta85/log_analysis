"""
File panel – macOS-style light theme.
* Directly lists log files in the directory with checkboxes.
* Check a file to load it instantly; uncheck to remove it.
* Log parsing runs in a background thread so the UI never freezes.
"""

import os
import threading
import tkinter as tk
from tkinter import filedialog
from pathlib import Path
from typing import Callable, List, Optional

from core.parser import LogParser, LogData
from ui.theme import (
    BG, BG2, LIST_BG, FG, FG2,
    BORDER, SEP, ACCENT, ACCENT_DARK, ACCENT_FG,
    SEL_BG, BTN_BG, BTN_FG, ENTRY_BG, DANGER,
    TAB_BG, STATE_CHIP,
)

DEFAULT_LOG_DIR = "/Users/giacinta/workspace/lumos_ws/logs"
LOG_EXTENSIONS  = {".out", ".info", ".log"}

STATE_LIST = [
    "RESET", "STAND", "RL_WALK", "RL_WALK_AMP",
    "RL_MIMIC", "RL_SITUP", "RL_LIEDOWN",
]


class FilePanel(tk.Frame):
    """
    Left-side master panel.
    Public API:
      get_active_logs()  -> List[LogData]
      get_state_filter() -> List[str]   (empty = show all)
    """

    def __init__(self, parent, on_data_changed: Callable, **kwargs):
        super().__init__(parent, bg=BG, **kwargs)
        self._on_data_changed   = on_data_changed
        self._parser            = LogParser()
        self._all_logs: List[LogData]         = []
        self._state_filter_vars: dict         = {}
        self._dir_files: List[Path]           = []
        self._dir_check_vars: List[tk.BooleanVar] = []
        self._dir_loaded_paths: set              = set()
        self._parsing = False
        self._build()
        self.after(150, self._refresh_dir_list)   # populate on startup

    # ── public API ────────────────────────────────────────────────────────────

    def get_active_logs(self) -> List[LogData]:
        return list(self._all_logs)

    def get_state_filter(self) -> List[str]:
        return [s for s, v in self._state_filter_vars.items() if v.get()]

    # ── build ─────────────────────────────────────────────────────────────────

    def _build(self):
        self.columnconfigure(0, weight=1)
        row = 0

        # ── Log Directory ────────────────────────────
        tk.Label(self, text="Log Directory", bg=BG, fg=FG,
                 font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, sticky="w", padx=8, pady=(8, 2))
        row += 1

        dir_row = tk.Frame(self, bg=BG)
        dir_row.grid(row=row, column=0, sticky="ew", padx=6, pady=(0, 4))
        dir_row.columnconfigure(0, weight=1)
        row += 1

        entry_wrap = tk.Frame(dir_row, bg=ENTRY_BG, highlightthickness=1,
                              highlightbackground=BORDER, highlightcolor=ACCENT)
        entry_wrap.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        dir_row.columnconfigure(0, weight=1)
        self._dir_var = tk.StringVar(value=DEFAULT_LOG_DIR)
        dir_entry = tk.Entry(entry_wrap, textvariable=self._dir_var,
                             font=("Helvetica", 8), bg=ENTRY_BG, fg=FG,
                             relief="flat", insertbackground=FG,
                             highlightthickness=0)
        dir_entry.pack(fill="x", padx=4, pady=3)
        dir_entry.bind("<Return>", lambda _: self._refresh_dir_list())

        tk.Button(dir_row, text="Browse", font=("Helvetica", 8),
                  bg=BTN_BG, fg=BTN_FG, relief="flat", padx=6, pady=2, bd=0,
                  highlightthickness=0, highlightbackground=BTN_BG,
                  overrelief="flat",
                  activebackground=SEL_BG, activeforeground=BTN_FG,
                  command=self._browse_dir).grid(row=0, column=1, sticky="e")

        # ── Available files browser ──────────────────
        hdr = tk.Frame(self, bg=BG)
        hdr.grid(row=row, column=0, sticky="ew", padx=6, pady=(2, 0))
        hdr.columnconfigure(0, weight=1)
        row += 1
        tk.Label(hdr, text="Available files", bg=BG, fg=FG,
                 font=("Helvetica", 10, "bold")).grid(row=0, column=0, sticky="w")
        tk.Button(hdr, text="⟳  Refresh", font=("Helvetica", 8),
                  bg=BG, fg=ACCENT, relief="flat", padx=0, bd=0,
                  highlightthickness=0, highlightbackground=BG,
                  overrelief="flat",
                  activebackground=BG, activeforeground=ACCENT,
                  cursor="hand2",
                  command=self._refresh_dir_list).grid(row=0, column=1, sticky="e")

        dir_outer = tk.Frame(self, bg=BORDER, bd=1, relief="flat")
        dir_outer.grid(row=row, column=0, sticky="nsew", padx=6, pady=(2, 0))
        self.rowconfigure(row, weight=2)
        row += 1

        dir_sb = tk.Scrollbar(dir_outer, width=10)
        dir_sb.pack(side=tk.RIGHT, fill=tk.Y)
        self._dir_cb_canvas = tk.Canvas(dir_outer, bg=LIST_BG,
                                        yscrollcommand=dir_sb.set,
                                        highlightthickness=0, bd=0)
        self._dir_cb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        dir_sb.config(command=self._dir_cb_canvas.yview)
        self._dir_cb_inner = tk.Frame(self._dir_cb_canvas, bg=LIST_BG)
        self._dir_cb_canvas.create_window((0, 0), window=self._dir_cb_inner, anchor="nw")
        self._dir_cb_inner.bind(
            "<Configure>",
            lambda e: self._dir_cb_canvas.configure(
                scrollregion=self._dir_cb_canvas.bbox("all")))

        tk.Label(self, text="勾选即加载，取消勾选即移除",
                 bg=BG, fg=FG2, font=("Helvetica", 7)).grid(
            row=row, column=0, sticky="w", padx=8, pady=(1, 2))
        row += 1

        self._draw_sep(row); row += 1

        # ── State filter ──────────────────────────────
        tk.Label(self, text="State filter", bg=BG, fg=FG,
                 font=("Helvetica", 10, "bold")).grid(
            row=row, column=0, sticky="w", padx=8, pady=(4, 0))
        row += 1

        state_frame = tk.Frame(self, bg=BG)
        state_frame.grid(row=row, column=0, sticky="ew", padx=8, pady=(2, 0))
        row += 1
        for s in STATE_LIST:
            v = tk.BooleanVar(value=False)
            self._state_filter_vars[s] = v
            chip_color = STATE_CHIP.get(s, BG2)
            cb = tk.Checkbutton(
                state_frame, text=s, variable=v,
                bg=BG, selectcolor=chip_color, fg=FG,
                activebackground=BG, activeforeground=FG,
                font=("Helvetica", 8),
                command=self._on_filter_change, anchor="w",
            )
            cb.pack(fill="x", pady=1)

        qf_frame = tk.Frame(self, bg=BG)
        qf_frame.grid(row=row, column=0, sticky="ew", padx=6, pady=(2, 4))
        row += 1
        for label, states in [
            ("All states", []),
            ("RL only", ["RL_WALK", "RL_WALK_AMP", "RL_MIMIC", "RL_SITUP"]),
        ]:
            tk.Button(qf_frame, text=label, font=("Helvetica", 8),
                      bg=BTN_BG, fg=BTN_FG, relief="flat", padx=8, pady=3,
                      highlightthickness=0, highlightbackground=BTN_BG,
                      bd=0, overrelief="flat",
                      activebackground=SEL_BG, activeforeground=BTN_FG,
                      command=lambda s=states: self._quick_filter(s)
                      ).pack(side=tk.LEFT, padx=(0, 4))

        self._draw_sep(row); row += 1

        # ── Status bar ────────────────────────────────
        self._status_var = tk.StringVar(value="勾选文件即可加载")
        tk.Label(self, textvariable=self._status_var, bg=BG, fg=FG2,
                 font=("Helvetica", 8), wraplength=205, justify="left").grid(
            row=row, column=0, sticky="w", padx=8, pady=(2, 6))

    def _draw_sep(self, row: int):
        tk.Frame(self, bg=SEP, height=1).grid(
            row=row, column=0, sticky="ew", padx=4, pady=2)

    # ── Directory browser ─────────────────────────────────────────────────────

    def _refresh_dir_list(self):
        for w in self._dir_cb_inner.winfo_children():
            w.destroy()
        self._dir_check_vars = []
        self._dir_files = []
        d = self._dir_var.get().strip()
        if not os.path.isdir(d):
            tk.Label(self._dir_cb_inner, text="  (invalid path)",
                     bg=LIST_BG, fg=FG2, font=("Helvetica", 8)).pack(anchor="w", padx=6, pady=4)
            return
        files = sorted(
            p for p in Path(d).iterdir()
            if p.is_file()
            and not p.name.startswith(".")
            and p.suffix.lower() in LOG_EXTENSIONS
        )
        if not files:
            tk.Label(self._dir_cb_inner, text="  (no log files found)",
                     bg=LIST_BG, fg=FG2, font=("Helvetica", 8)).pack(anchor="w", padx=6, pady=4)
            return
        self._dir_files = files
        for i, p in enumerate(files):
            kb = p.stat().st_size // 1024
            size_str = f"{kb // 1024:.0f}MB" if kb >= 1024 else f"{kb}KB"
            v = tk.BooleanVar(value=str(p) in self._dir_loaded_paths)
            self._dir_check_vars.append(v)
            row_f = tk.Frame(self._dir_cb_inner, bg=LIST_BG)
            row_f.pack(fill="x", padx=2, pady=1)
            tk.Checkbutton(
                row_f, variable=v,
                bg=LIST_BG, selectcolor=ACCENT, fg=FG,
                activebackground=LIST_BG, activeforeground=FG,
                highlightthickness=0, highlightbackground=LIST_BG,
                font=("Courier", 8), anchor="w",
                command=lambda idx=i, var=v: self._on_dir_check(idx, var),
            ).pack(side=tk.LEFT)
            tk.Label(row_f, text=p.name, bg=LIST_BG, fg=FG,
                     font=("Courier", 8), anchor="w").pack(side=tk.LEFT, fill="x", expand=True)
            tk.Label(row_f, text=f"[{size_str}]", bg=LIST_BG, fg=FG2,
                     font=("Helvetica", 7)).pack(side=tk.RIGHT, padx=2)

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self._dir_var.get())
        if d:
            self._dir_var.set(d)
            self._refresh_dir_list()

    def _on_dir_check(self, idx: int, var: tk.BooleanVar):
        """Called when user clicks a checkbox in the available-files list."""
        if idx >= len(self._dir_files):
            return
        path = str(self._dir_files[idx])
        if var.get():
            if path not in self._dir_loaded_paths:
                self._dir_loaded_paths.add(path)
                self._load_paths_async([path])
        else:
            if path in self._dir_loaded_paths:
                self._dir_loaded_paths.discard(path)
                self._all_logs = [l for l in self._all_logs if l.filepath != path]
                self._status_var.set(f"{len(self._all_logs)} file(s) loaded")
                self._on_data_changed()

    # ── Parsing (background thread) ───────────────────────────────────────────

    def _load_paths_async(self, paths: List[str]):
        if self._parsing:
            self._status_var.set("Already parsing – please wait…")
            return
        self._parsing = True
        n = len(paths)
        self._status_var.set(f"Parsing {n} file(s)…  (UI stays responsive)")
        self.update_idletasks()

        def _worker():
            loaded, errors = [], []
            for p in paths:
                try:
                    loaded.append(self._parser.parse_file(p))
                except Exception as exc:
                    errors.append(f"{Path(p).name}: {exc}")
            self.after(0, lambda: self._on_parse_done(loaded, errors))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_parse_done(self, loaded: List[LogData], errors: List[str]):
        self._parsing = False
        self._all_logs.extend(loaded)
        msg = f"{len(self._all_logs)} file(s) loaded"
        if errors:
            msg += f"\n⚠ {'; '.join(errors[:2])}"
        self._status_var.set(msg)
        self._on_data_changed()

    # ── Loaded list ───────────────────────────────────────────────────────────

    def _clear_all(self):
        self._dir_loaded_paths.clear()
        self._all_logs.clear()
        for v in self._dir_check_vars:
            v.set(False)
        self._status_var.set("All files cleared.")
        self._on_data_changed()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _quick_filter(self, states: List[str]):
        if not states:
            for v in self._state_filter_vars.values():
                v.set(False)
        else:
            for s, v in self._state_filter_vars.items():
                v.set(s in states)
        self._on_filter_change()

    def _on_filter_change(self):
        self._on_data_changed()
