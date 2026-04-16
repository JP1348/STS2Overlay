"""
ui/login_dialog.py

One-time login/register dialog.
Appears only if no saved token found. After login the token is stored
on disk — player never sees this again unless they log out.
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from core.api_client import ApiClient


class LoginDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, client: ApiClient, on_success: Optional[Callable] = None):
        super().__init__(parent)
        self._client = client
        self._on_success = on_success

        self.title("STS2 Advisor — Sign In")
        self.resizable(False, False)
        self.configure(bg="#1a1a2e")
        self.attributes("-topmost", True)

        self._build()
        self._center(parent)

    def _build(self):
        PAD = {"padx": 14, "pady": 6}
        BG, FG, ACC = "#1a1a2e", "#e8d5a3", "#c9a84c"
        ENTRY_BG = "#2a2a4e"

        tk.Label(self, text="STS2 Advisor", font=("Georgia", 16, "bold"),
                 bg=BG, fg=ACC).pack(pady=(16, 2))
        tk.Label(self, text="Community login — your runs make everyone smarter",
                 font=("Arial", 9), bg=BG, fg="#888").pack(pady=(0, 12))

        frame = tk.Frame(self, bg=BG)
        frame.pack(padx=24, pady=4)

        def lbl(text):
            tk.Label(frame, text=text, bg=BG, fg=FG, font=("Arial", 10),
                     anchor="w", width=12).grid(row=lbl.row, column=0, sticky="w", **PAD)
            lbl.row += 1
        lbl.row = 0

        def ent(show=""):
            e = tk.Entry(frame, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                         relief="flat", font=("Arial", 10), show=show)
            e.grid(row=ent.row, column=1, **PAD, ipadx=6, ipady=4)
            ent.row += 1
            return e
        ent.row = 0

        lbl("Username")
        self._user_entry = ent()

        lbl("Password")
        self._pass_entry = ent(show="•")

        # Email row — hidden by default, shown on Register tab
        self._email_label = tk.Label(frame, text="Email", bg=BG, fg=FG, font=("Arial", 10),
                                     anchor="w", width=12)
        self._email_entry = tk.Entry(frame, bg=ENTRY_BG, fg=FG, insertbackground=FG,
                                     relief="flat", font=("Arial", 10))
        # Don't grid email yet

        # Status message
        self._status_var = tk.StringVar(value="")
        tk.Label(self, textvariable=self._status_var, bg=BG, fg="#e05c5c",
                 font=("Arial", 9), wraplength=280).pack(pady=4)

        # Buttons
        btn_frame = tk.Frame(self, bg=BG)
        btn_frame.pack(pady=(4, 16))

        self._mode = tk.StringVar(value="login")

        tk.Button(btn_frame, text="Login", width=12,
                  bg=ACC, fg="#1a1a2e", font=("Arial", 10, "bold"),
                  relief="flat", cursor="hand2",
                  command=self._do_login).grid(row=0, column=0, padx=6)

        tk.Button(btn_frame, text="Register", width=12,
                  bg="#3a3a5e", fg=FG, font=("Arial", 10),
                  relief="flat", cursor="hand2",
                  command=self._toggle_register).grid(row=0, column=1, padx=6)

        tk.Button(btn_frame, text="Skip (offline)", width=14,
                  bg="#2a2a4e", fg="#666", font=("Arial", 9),
                  relief="flat", cursor="hand2",
                  command=self._skip).grid(row=1, column=0, columnspan=2, pady=(8, 0))

        self._login_btn = btn_frame.winfo_children()[0]
        self._reg_btn   = btn_frame.winfo_children()[1]
        self._frame = frame

    def _toggle_register(self):
        if self._mode.get() == "login":
            self._mode.set("register")
            self._email_label.grid(row=2, column=0, padx=14, pady=6, sticky="w")
            self._email_entry.grid(row=2, column=1, padx=14, pady=6, ipadx=6, ipady=4)
            self._login_btn.configure(text="Create Account", command=self._do_register)
            self._reg_btn.configure(text="Back to Login", command=self._toggle_register)
        else:
            self._mode.set("login")
            self._email_label.grid_remove()
            self._email_entry.grid_remove()
            self._login_btn.configure(text="Login", command=self._do_login)
            self._reg_btn.configure(text="Register", command=self._toggle_register)

    def _do_login(self):
        u = self._user_entry.get().strip()
        p = self._pass_entry.get()
        if not u or not p:
            self._status_var.set("Enter username and password.")
            return
        self._status_var.set("Logging in...")
        self.update()
        ok, msg = self._client.login(u, p)
        if ok:
            self._finish(msg)
        else:
            self._status_var.set(msg)

    def _do_register(self):
        u = self._user_entry.get().strip()
        e = self._email_entry.get().strip()
        p = self._pass_entry.get()
        if not u or not e or not p:
            self._status_var.set("Fill in all fields.")
            return
        self._status_var.set("Creating account...")
        self.update()
        ok, msg = self._client.register(u, e, p)
        if ok:
            self._finish(msg)
        else:
            self._status_var.set(msg)

    def _finish(self, msg: str):
        if self._on_success:
            self._on_success(msg)
        self.destroy()

    def _skip(self):
        """Offline mode — no data submission, no seed intel."""
        self.destroy()

    def _center(self, parent: tk.Tk):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")
