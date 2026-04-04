"""
Setup / Settings window — built with CustomTkinter.
Opens on first run or when "Settings" is clicked from the tray.
"""

import threading
import tkinter as tk
import webbrowser

import customtkinter as ctk

import config
import monitor

APP_PASSWORD_HELP_URL = "https://myaccount.google.com/apppasswords"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SetupWindow(ctk.CTkToplevel):
    def __init__(self, master, on_save, existing_config=None):
        super().__init__(master)
        self.on_save = on_save
        self.title("Zelle Notifier — Setup")
        self.geometry("440x520")
        self.resizable(False, False)
        self.lift()
        self.focus_force()
        self._build(existing_config or {})

    def _build(self, cfg):
        pad = {"padx": 32, "pady": 6}

        # ── Header ──────────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="Zelle Notifier",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(28, 2))

        ctk.CTkLabel(
            self,
            text="Your PC will announce Zelle payments out loud\nthe moment they arrive in Gmail.",
            font=ctk.CTkFont(size=13),
            text_color="#9ca3af",
            justify="center",
        ).pack(pady=(0, 20))

        # ── Gmail address ────────────────────────────────────────────────
        ctk.CTkLabel(
            self,
            text="Gmail Address",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", **pad)

        self._gmail_var = tk.StringVar(value=cfg.get("gmail", ""))
        ctk.CTkEntry(
            self,
            textvariable=self._gmail_var,
            placeholder_text="yourstore@gmail.com",
            height=38,
        ).pack(fill="x", **pad)

        # ── App Password ─────────────────────────────────────────────────
        pw_row = ctk.CTkFrame(self, fg_color="transparent")
        pw_row.pack(fill="x", padx=32, pady=(12, 0))
        ctk.CTkLabel(
            pw_row,
            text="Gmail App Password",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            pw_row,
            text="How to get one ->",
            font=ctk.CTkFont(size=12),
            text_color="#60a5fa",
            fg_color="transparent",
            hover_color="#1f2937",
            command=lambda: webbrowser.open(APP_PASSWORD_HELP_URL),
            width=0,
            cursor="hand2",
        ).pack(side="right")

        self._pw_var = tk.StringVar(value=cfg.get("app_password", ""))
        self._pw_visible = False
        pw_frame = ctk.CTkFrame(self, fg_color="transparent")
        pw_frame.pack(fill="x", padx=32, pady=6)
        self._pw_entry = ctk.CTkEntry(
            pw_frame,
            textvariable=self._pw_var,
            placeholder_text="xxxx xxxx xxxx xxxx",
            show="*",
            height=38,
        )
        self._pw_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            pw_frame,
            text="show",
            width=52,
            height=38,
            command=self._toggle_pw,
            fg_color="#374151",
            hover_color="#4b5563",
        ).pack(side="right")

        ctk.CTkLabel(
            self,
            text="Not your Gmail password — a special 16-character code\nfrom Google Account > Security > App passwords.",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
            justify="left",
        ).pack(fill="x", padx=32, pady=(2, 14))

        # ── Status label ─────────────────────────────────────────────────
        self._status_label = ctk.CTkLabel(
            self, text="", font=ctk.CTkFont(size=13), height=24
        )
        self._status_label.pack(**pad)

        # ── Buttons ───────────────────────────────────────────────────────
        self._test_btn = ctk.CTkButton(
            self,
            text="Test Connection",
            height=40,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._test_connection,
        )
        self._test_btn.pack(fill="x", padx=32, pady=(4, 6))

        self._save_btn = ctk.CTkButton(
            self,
            text="Save & Start Monitoring",
            height=44,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._save,
        )
        self._save_btn.pack(fill="x", padx=32, pady=(0, 28))

    # ── Helpers ───────────────────────────────────────────────────────────

    def _toggle_pw(self):
        self._pw_visible = not self._pw_visible
        self._pw_entry.configure(show="" if self._pw_visible else "*")

    def _set_status(self, text, color="#9ca3af"):
        self._status_label.configure(text=text, text_color=color)

    def _test_connection(self):
        gmail = self._gmail_var.get().strip()
        pw = self._pw_var.get().strip()
        if not gmail or not pw:
            self._set_status("Fill in both fields first.", "#f59e0b")
            return
        self._test_btn.configure(state="disabled", text="Testing...")
        self._set_status("Connecting to Gmail...", "#9ca3af")

        def run():
            ok, msg = monitor.test_credentials(gmail, pw)
            self.after(0, lambda: self._on_test_result(ok, msg))

        threading.Thread(target=run, daemon=True).start()

    def _on_test_result(self, ok, msg):
        self._test_btn.configure(state="normal", text="Test Connection")
        self._set_status(
            ("OK  " if ok else "X  ") + msg,
            "#22c55e" if ok else "#ef4444",
        )

    def _save(self):
        gmail = self._gmail_var.get().strip()
        pw = self._pw_var.get().strip()
        if not gmail or not pw:
            self._set_status("Both fields are required.", "#f59e0b")
            return
        config.save(gmail, pw)
        self.on_save(gmail, pw, "")
        self.withdraw()


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self._setup_win = None

    def open_settings(self, on_save, existing_config=None):
        if self._setup_win and self._setup_win.winfo_exists():
            self._setup_win.lift()
            self._setup_win.focus_force()
            return
        self._setup_win = SetupWindow(
            self, on_save=on_save, existing_config=existing_config
        )
