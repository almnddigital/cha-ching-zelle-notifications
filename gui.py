"""
Setup / Settings window — built with CustomTkinter.
Opens on first run or when "Settings" is clicked from the tray.
"""

import threading
import tkinter as tk
import webbrowser
from datetime import datetime

import customtkinter as ctk

import config
import monitor
import payment_history

APP_PASSWORD_HELP_URL = "https://myaccount.google.com/apppasswords"

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SetupWindow(ctk.CTkToplevel):
    def __init__(self, master, on_save, existing_config=None):
        super().__init__(master)
        self.on_save = on_save
        self.title("Cha-Ching Payment Notifications — Setup")
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
            text="Cha-Ching Payment Notifications",
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


def _format_history_date(value):
    try:
        parsed = datetime.fromisoformat(value).astimezone()
        return parsed.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")
    except (TypeError, ValueError):
        return value or "Unknown date"


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, master, on_backfill):
        super().__init__(master)
        self._on_backfill = on_backfill
        self._backfill_running = False
        self.title("Payment History")
        self.geometry("680x620")
        self.minsize(560, 460)
        self._build()
        self.refresh()
        self.lift()
        self.focus_force()

    def _build(self):
        ctk.CTkLabel(
            self,
            text="Payment History",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(pady=(24, 2))
        self._summary = ctk.CTkLabel(self, text="", text_color="#9ca3af")
        self._summary.pack(pady=(0, 14))

        self._rows = ctk.CTkScrollableFrame(self, corner_radius=8)
        self._rows.pack(fill="both", expand=True, padx=24, pady=(0, 14))

        backfill_panel = ctk.CTkFrame(self, fg_color="#111827")
        backfill_panel.pack(fill="x", padx=24, pady=(0, 14))
        ctk.CTkLabel(
            backfill_panel,
            text="One-time Gmail import",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            backfill_panel,
            text="Import older Zelle payments without announcing them.",
            text_color="#9ca3af",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 8))
        backfill_controls = ctk.CTkFrame(backfill_panel, fg_color="transparent")
        backfill_controls.pack(fill="x", padx=14, pady=(0, 4))
        self._backfill_length = tk.StringVar(value="1 year")
        self._backfill_picker = ctk.CTkOptionMenu(
            backfill_controls,
            variable=self._backfill_length,
            values=["1 year", "2 years", "Max"],
            width=120,
        )
        self._backfill_picker.pack(side="left")
        self._backfill_btn = ctk.CTkButton(
            backfill_controls,
            text="Import once",
            width=130,
            command=self._start_backfill,
        )
        self._backfill_btn.pack(side="right")
        self._backfill_status = ctk.CTkLabel(
            backfill_panel,
            text="",
            text_color="#9ca3af",
            anchor="w",
        )
        self._backfill_status.pack(fill="x", padx=14, pady=(2, 12))

        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(fill="x", padx=24, pady=(0, 20))
        ctk.CTkButton(
            button_row,
            text="Refresh",
            width=100,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self.refresh,
        ).pack(side="left")
        ctk.CTkButton(
            button_row,
            text="Close",
            width=100,
            command=self.destroy,
        ).pack(side="right")

    def refresh(self):
        records = payment_history.load()
        total = payment_history.total_amount(records)
        self._summary.configure(
            text=f"{len(records)} payment(s)  •  Known total: ${total:,.2f}"
        )
        backfill_state = payment_history.load_backfill_state()
        if backfill_state:
            self._backfill_length.set(backfill_state.get("length", "1 year"))
            self._backfill_picker.configure(state="disabled")
            self._backfill_btn.configure(state="disabled", text="Import complete")
            self._backfill_status.configure(
                text=(
                    "Completed once: "
                    f"{backfill_state.get('imported_count', 0)} payment(s) imported."
                ),
                text_color="#22c55e",
            )
        elif not self._backfill_running:
            self._backfill_picker.configure(state="normal")
            self._backfill_btn.configure(state="normal", text="Import once")
            self._backfill_status.configure(
                text="Choose a range. This import can only run once.",
                text_color="#9ca3af",
            )
        for child in self._rows.winfo_children():
            child.destroy()

        header = ctk.CTkFrame(self._rows, fg_color="#1f2937")
        header.pack(fill="x", pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="DATE", anchor="w").grid(
            row=0, column=0, sticky="ew", padx=12, pady=8
        )
        ctk.CTkLabel(header, text="FROM", anchor="w").grid(
            row=0, column=1, sticky="ew", padx=12, pady=8
        )
        ctk.CTkLabel(header, text="AMOUNT", anchor="e").grid(
            row=0, column=2, sticky="e", padx=12, pady=8
        )

        if not records:
            ctk.CTkLabel(
                self._rows,
                text="No payments recorded yet.",
                text_color="#9ca3af",
            ).pack(pady=32)
            return

        for record in records:
            row = ctk.CTkFrame(self._rows, fg_color="transparent")
            row.pack(fill="x", pady=1)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(
                row,
                text=_format_history_date(record.get("received_at")),
                anchor="w",
                text_color="#d1d5db",
            ).grid(row=0, column=0, sticky="ew", padx=12, pady=7)
            ctk.CTkLabel(
                row,
                text=record.get("name", "Unknown sender"),
                anchor="w",
                text_color="#f3f4f6",
            ).grid(row=0, column=1, sticky="ew", padx=12, pady=7)
            ctk.CTkLabel(
                row,
                text=record.get("amount", "Unknown amount"),
                anchor="e",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color="#22c55e",
            ).grid(row=0, column=2, sticky="e", padx=12, pady=7)

    def _start_backfill(self):
        if self._backfill_running or payment_history.load_backfill_state():
            return
        self._backfill_running = True
        length = self._backfill_length.get()
        self._backfill_picker.configure(state="disabled")
        self._backfill_btn.configure(state="disabled", text="Importing...")
        self._backfill_status.configure(
            text="Scanning Gmail. This may take a while...",
            text_color="#f59e0b",
        )

        def run():
            try:
                matched_count, imported_count = self._on_backfill(length)
            except Exception as exc:
                self.after(0, lambda: self._backfill_failed(str(exc)))
                return
            self.after(
                0,
                lambda: self._backfill_finished(matched_count, imported_count),
            )

        threading.Thread(target=run, daemon=True).start()

    def _backfill_finished(self, matched_count, imported_count):
        self._backfill_running = False
        self.refresh()
        self._backfill_status.configure(
            text=(
                f"Import complete: {imported_count} new payment(s) "
                f"from {matched_count} matching email(s)."
            ),
            text_color="#22c55e",
        )

    def _backfill_failed(self, message):
        self._backfill_running = False
        self._backfill_picker.configure(state="normal")
        self._backfill_btn.configure(state="normal", text="Import once")
        self._backfill_status.configure(
            text=message,
            text_color="#ef4444",
        )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.withdraw()
        self._setup_win = None
        self._history_win = None

    def open_settings(self, on_save, existing_config=None):
        if self._setup_win and self._setup_win.winfo_exists():
            self._setup_win.lift()
            self._setup_win.focus_force()
            return
        self._setup_win = SetupWindow(
            self, on_save=on_save, existing_config=existing_config
        )

    def open_history(self, on_backfill):
        if self._history_win and self._history_win.winfo_exists():
            self._history_win.refresh()
            self._history_win.lift()
            self._history_win.focus_force()
            return
        self._history_win = HistoryWindow(self, on_backfill)
