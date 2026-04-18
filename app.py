#!/usr/bin/env python3
"""
Lumos Log Analyzer – entry point.
Run: python app.py
"""

import sys
import os
import traceback

# Ensure the app root is on sys.path regardless of where it is launched from
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

# Set matplotlib backend BEFORE any other matplotlib/tkinter imports
import matplotlib
matplotlib.use("TkAgg")

import matplotlib.pyplot as plt
plt.rcParams.update({
    "font.family":        "DejaVu Sans",
    "axes.unicode_minus": False,
    "figure.autolayout":  False,
})

import tkinter as tk
from tkinter import messagebox, ttk

from ui.main_window import MainWindow
from ui.theme import BG, BG2, FG, ENTRY_BG, LIST_BG, SEL_BG, BTN_BG, BTN_FG, BORDER, ACCENT


def _apply_ttk_style(root: tk.Tk):
    """Override ttk widget styles to use the forced-light theme."""
    s = ttk.Style(root)
    # Use 'default' as the base (avoids macOS Aqua dark-mode interference)
    s.theme_use("default")
    s.configure("TCombobox",
                fieldbackground=ENTRY_BG,
                background=BTN_BG,
                foreground=FG,
                selectbackground=SEL_BG,
                selectforeground=FG,
                bordercolor=BORDER,
                lightcolor=BORDER,
                darkcolor=BORDER,
                arrowcolor=FG,
                padding=3)
    s.map("TCombobox",
          fieldbackground=[("readonly", ENTRY_BG), ("disabled", BG2)],
          foreground=[("disabled", "#888888")])
    # Scrollbar
    s.configure("TScrollbar", troughcolor=BG2, background=BTN_BG, bordercolor=BORDER)


def main():
    root = tk.Tk()
    root.withdraw()   # hide until fully built to avoid flash

    # Remove dark focus ring that appears under/around buttons on macOS
    root.option_add("*Button.highlightThickness", 0)
    root.option_add("*Button.borderWidth", 0)
    root.option_add("*Button.relief", "flat")

    _apply_ttk_style(root)

    try:
        app = MainWindow(root)
    except Exception as e:
        root.deiconify()
        messagebox.showerror("Startup Error", traceback.format_exc())
        root.destroy()
        sys.exit(1)

    root.deiconify()
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()


if __name__ == "__main__":
    main()
