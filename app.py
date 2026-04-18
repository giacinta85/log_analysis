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
from tkinter import messagebox

from ui.main_window import MainWindow


def main():
    root = tk.Tk()
    root.withdraw()   # hide until fully built to avoid flash

    # Remove dark focus ring that appears under/around buttons on macOS
    root.option_add("*Button.highlightThickness", 0)
    root.option_add("*Button.borderWidth", 0)
    root.option_add("*Button.relief", "flat")

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
