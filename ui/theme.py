"""
macOS-style forced-light theme constants.
All colours are hardcoded so the app is unaffected by system dark mode.
"""

# Backgrounds
BG        = "#f5f5f7"   # main window / panels
BG2       = "#ebebed"   # slightly darker sections
LIST_BG   = "#ffffff"   # listbox / table background
CANVAS_BG = "#f5f5f7"

# Text
FG        = "#1d1d1f"   # primary text  (macOS near-black)
FG2       = "#6e6e73"   # secondary / caption text
FG_INVERT = "#ffffff"

# Borders & separators
BORDER    = "#d2d2d7"
SEP       = "#d2d2d7"

# Interactive
ACCENT      = "#0071e3"   # macOS system blue
ACCENT_DARK = "#0051a8"
ACCENT_FG   = "#ffffff"
SEL_BG      = "#ddeeff"
BTN_BG      = "#e8e8ed"
BTN_FG      = "#1d1d1f"
BTN_HOVER   = "#d8d8dd"
ENTRY_BG    = "#ffffff"
DANGER      = "#ff3b30"   # macOS red

# Tab bar
TAB_BG      = "#e8e8ed"
TAB_ACTIVE  = "#ffffff"
TAB_ACTIVE_FG = "#0071e3"
TAB_FG      = "#6e6e73"

# State segment colours (used in charts + checkbutton backgrounds)
STATE_CHIP: dict = {
    "RESET":       "#e0e0e0",
    "STAND":       "#c5dff5",
    "RL_WALK":     "#c5f0d0",
    "RL_WALK_AMP": "#fce8c0",
    "RL_MIMIC":    "#e8c8f5",
    "RL_SITUP":    "#f5c8c8",
    "RL_LIEDOWN":  "#d8d8d8",
    "UNKNOWN":     "#f0f0f0",
}
