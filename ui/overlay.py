"""
overlay.py
Simple always-on-top overlay window using tkinter.
Displays current run state and advisor tips.
Stays transparent/minimal — player can toggle visibility with a hotkey.
"""

import tkinter as tk
from tkinter import font as tkfont
import threading


OVERLAY_WIDTH  = 320
OVERLAY_HEIGHT = 480
OPACITY        = 0.88        # 0.0 = invisible, 1.0 = fully opaque
BG_COLOR       = "#0d0d0d"
TEXT_COLOR     = "#e8d8b0"   # parchment-ish, fits STS aesthetic
ACCENT_COLOR   = "#c89a3c"   # gold
GOOD_COLOR     = "#6fcf6f"   # green for "take" advice
WARN_COLOR     = "#cf6f6f"   # red for "skip" advice


class OverlayWindow:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("STS2 Advisor")
        self.root.geometry(f"{OVERLAY_WIDTH}x{OVERLAY_HEIGHT}+20+20")
        self.root.configure(bg=BG_COLOR)
        self.root.attributes("-topmost", True)       # always on top
        self.root.attributes("-alpha", OPACITY)
        self.root.overrideredirect(False)            # keep title bar for dragging

        self._build_ui()
        self._bind_hotkeys()

    def _build_ui(self):
        title_font  = tkfont.Font(family="Helvetica", size=11, weight="bold")
        label_font  = tkfont.Font(family="Helvetica", size=9,  weight="bold")
        normal_font = tkfont.Font(family="Helvetica", size=9)
        tip_font    = tkfont.Font(family="Helvetica", size=9,  slant="italic")

        # --- Header ---
        header = tk.Frame(self.root, bg=BG_COLOR)
        header.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(header, text="STS2 Advisor", font=title_font,
                 bg=BG_COLOR, fg=ACCENT_COLOR).pack(side="left")
        self.status_label = tk.Label(header, text="● Waiting...", font=normal_font,
                                     bg=BG_COLOR, fg="#888888")
        self.status_label.pack(side="right")

        tk.Frame(self.root, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=8, pady=4)

        # --- Run Info ---
        info_frame = tk.Frame(self.root, bg=BG_COLOR)
        info_frame.pack(fill="x", padx=8)

        self.info_text = tk.StringVar(value="No run loaded.\nPoint to your STS2 save folder.")
        tk.Label(info_frame, textvariable=self.info_text, font=normal_font,
                 bg=BG_COLOR, fg=TEXT_COLOR, justify="left", anchor="w").pack(fill="x")

        tk.Frame(self.root, bg="#333333", height=1).pack(fill="x", padx=8, pady=6)

        # --- Advice Panel ---
        tk.Label(self.root, text="Advisor Tips", font=label_font,
                 bg=BG_COLOR, fg=ACCENT_COLOR, anchor="w").pack(fill="x", padx=8)

        self.advice_frame = tk.Frame(self.root, bg=BG_COLOR)
        self.advice_frame.pack(fill="both", expand=True, padx=8, pady=4)

        self.advice_text = tk.Text(
            self.advice_frame, bg=BG_COLOR, fg=TEXT_COLOR,
            font=tip_font, wrap="word", relief="flat",
            state="disabled", height=12
        )
        self.advice_text.pack(fill="both", expand=True)
        self.advice_text.tag_configure("good", foreground=GOOD_COLOR)
        self.advice_text.tag_configure("warn", foreground=WARN_COLOR)
        self.advice_text.tag_configure("neutral", foreground=TEXT_COLOR)

        # --- Footer ---
        tk.Frame(self.root, bg=ACCENT_COLOR, height=1).pack(fill="x", padx=8, pady=4)
        tk.Label(self.root, text="Ctrl+H: Hide/Show   |   STS2 Advisor v0.1",
                 font=tkfont.Font(family="Helvetica", size=7),
                 bg=BG_COLOR, fg="#555555").pack(pady=(0, 6))

    def _bind_hotkeys(self):
        self.root.bind("<Control-h>", self._toggle_visibility)
        self._visible = True

    def _toggle_visibility(self, event=None):
        if self._visible:
            self.root.withdraw()
        else:
            self.root.deiconify()
        self._visible = not self._visible

    def update_run_info(self, run_state):
        """Update the run info panel from a RunState object."""
        text = (
            f"Char:   {run_state.character or '?'}\n"
            f"Seed:   {run_state.seed or '?'}\n"
            f"Asc:    {run_state.ascension}   "
            f"Act {run_state.act}  |  Floor {run_state.floor}\n"
            f"HP:     {run_state.hp} / {run_state.max_hp}\n"
            f"Gold:   {run_state.gold}\n"
            f"Deck:   {len(run_state.deck)} cards\n"
            f"Relics: {len(run_state.relics)}"
        )
        self.root.after(0, lambda: self.info_text.set(text))
        self.root.after(0, lambda: self.status_label.config(
            text="● Active", fg=GOOD_COLOR))

    def update_advice(self, tips: list):
        """
        tips: list of dicts with keys 'text' and 'tone' ('good', 'warn', 'neutral')
        """
        def _update():
            self.advice_text.config(state="normal")
            self.advice_text.delete("1.0", "end")
            for tip in tips:
                tag  = tip.get("tone", "neutral")
                text = tip.get("text", "")
                self.advice_text.insert("end", f"• {text}\n", tag)
            self.advice_text.config(state="disabled")
        self.root.after(0, _update)

    def show_error(self, message: str):
        self.root.after(0, lambda: self.status_label.config(
            text="● Error", fg=WARN_COLOR))
        self.update_advice([{"text": message, "tone": "warn"}])

    def run(self):
        self.root.mainloop()
