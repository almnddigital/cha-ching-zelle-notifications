"""
Setup / Settings window — built with CustomTkinter.
Opens on first run or when "Settings" is clicked from the tray.
"""

import logging
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from tkinter import ttk

import customtkinter as ctk

import config
import monitor
import payment_history

APP_PASSWORD_HELP_URL = "https://myaccount.google.com/apppasswords"
BACKFILL_LENGTHS = ["1 year", "2 years", "Max"]
BACKFILL_ORDER = {length: index for index, length in enumerate(BACKFILL_LENGTHS)}
HISTORY_PAGE_SIZE = 100

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class SetupWindow(ctk.CTkToplevel):
    def __init__(self, master, on_save, existing_config=None, startup_error=None):
        super().__init__(master)
        self.on_save = on_save
        self.title("Cha-Ching Payment Notifications — Setup")
        self.geometry("440x520")
        self.resizable(False, False)
        self.lift()
        self.focus_force()
        self._build(existing_config or {})
        if startup_error:
            self._set_status(startup_error, "#ef4444")

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
        self._save_btn.configure(state="disabled", text="Saving...")
        try:
            config.save(gmail, pw)
            self.on_save(gmail, pw, "")
        except Exception as exc:
            logging.exception("Could not save settings or start monitoring")
            self._save_btn.configure(state="normal", text="Save & Start Monitoring")
            self._set_status(f"Could not start monitoring: {exc}", "#ef4444")
            return
        self._set_status("Saved. Monitoring started.", "#22c55e")
        self.after(250, self.withdraw)


def _format_history_date(value):
    try:
        parsed = datetime.fromisoformat(value).astimezone()
        return parsed.strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")
    except (TypeError, ValueError):
        return value or "Unknown date"


def _format_history_sender(record):
    return payment_history.payer_display(record)


class HistoryWindow(ctk.CTkToplevel):
    def __init__(self, master, on_backfill):
        super().__init__(master)
        self.withdraw()
        self._on_backfill = on_backfill
        self._backfill_running = False
        self._backfill_cancel = threading.Event()
        self._backfill_mode = "import"
        self._records = []
        self._filtered_records = []
        self._page = 0
        self._history_error = None
        self.title("Payment History")
        self.geometry("680x620")
        self.minsize(560, 460)
        self._build()
        self.refresh()
        self.update_idletasks()
        self.deiconify()
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

        search_row = ctk.CTkFrame(self, fg_color="transparent")
        search_row.pack(fill="x", padx=24, pady=(0, 10))
        self._search_var = tk.StringVar()
        self._search_entry = ctk.CTkEntry(
            search_row,
            textvariable=self._search_var,
            placeholder_text="Search name, email, amount, or date",
            height=36,
        )
        self._search_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        ctk.CTkButton(
            search_row,
            text="Search",
            width=90,
            command=self._apply_search,
        ).pack(side="right")
        self._search_entry.bind("<Return>", lambda _event: self._apply_search())

        table = ctk.CTkFrame(self, corner_radius=8)
        table.pack(fill="both", expand=True, padx=24, pady=(0, 14))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "ChaChing.Treeview",
            background="#111827",
            fieldbackground="#111827",
            foreground="#f3f4f6",
            rowheight=32,
            borderwidth=0,
        )
        style.configure(
            "ChaChing.Treeview.Heading",
            background="#1f2937",
            foreground="#d1d5db",
            relief="flat",
        )
        style.map("ChaChing.Treeview", background=[("selected", "#1d4ed8")])
        self._rows = ttk.Treeview(
            table,
            columns=("date", "sender", "amount"),
            show="headings",
            style="ChaChing.Treeview",
            selectmode="browse",
        )
        self._rows.heading("date", text="DATE")
        self._rows.heading("sender", text="PAYER")
        self._rows.heading("amount", text="AMOUNT")
        self._rows.column("date", width=175, minwidth=150, anchor="w")
        self._rows.column("sender", width=330, minwidth=220, anchor="w")
        self._rows.column("amount", width=110, minwidth=90, anchor="e")
        scrollbar = ctk.CTkScrollbar(table, command=self._rows.yview)
        self._rows.configure(yscrollcommand=scrollbar.set)
        self._rows.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scrollbar.pack(side="right", fill="y", padx=(4, 8), pady=8)

        pagination_row = ctk.CTkFrame(self, fg_color="transparent")
        pagination_row.pack(fill="x", padx=24, pady=(0, 14))
        self._previous_btn = ctk.CTkButton(
            pagination_row,
            text="Previous",
            width=100,
            fg_color="#374151",
            hover_color="#4b5563",
            command=lambda: self._change_page(-1),
        )
        self._previous_btn.pack(side="left")
        self._page_label = ctk.CTkLabel(pagination_row, text="")
        self._page_label.pack(side="left", expand=True)
        self._next_btn = ctk.CTkButton(
            pagination_row,
            text="Next",
            width=100,
            fg_color="#374151",
            hover_color="#4b5563",
            command=lambda: self._change_page(1),
        )
        self._next_btn.pack(side="right")

        backfill_panel = ctk.CTkFrame(self, fg_color="#111827")
        backfill_panel.pack(fill="x", padx=24, pady=(0, 14))
        ctk.CTkLabel(
            backfill_panel,
            text="Gmail payment import",
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w",
        ).pack(fill="x", padx=14, pady=(12, 2))
        ctk.CTkLabel(
            backfill_panel,
            text="Import, expand, or rebuild Zelle history without announcements.",
            text_color="#9ca3af",
            anchor="w",
        ).pack(fill="x", padx=14, pady=(0, 8))
        backfill_controls = ctk.CTkFrame(backfill_panel, fg_color="transparent")
        backfill_controls.pack(fill="x", padx=14, pady=(0, 4))
        self._backfill_length = tk.StringVar(value="1 year")
        self._backfill_picker = ctk.CTkOptionMenu(
            backfill_controls,
            variable=self._backfill_length,
            values=BACKFILL_LENGTHS,
            width=120,
            command=self._backfill_selection_changed,
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
        try:
            self._records = payment_history.load()
            self._history_error = None
            self._update_backfill_controls()
        except payment_history.HistoryReadError as exc:
            logging.exception("Could not load payment history")
            self._records = []
            self._history_error = str(exc)
            self._backfill_picker.configure(state="disabled")
            self._backfill_btn.configure(state="disabled", text="Unavailable")
            self._backfill_status.configure(
                text="History storage must be recovered before importing.",
                text_color="#ef4444",
            )
        self._apply_search()

    def _apply_search(self):
        query = self._search_var.get().strip().casefold()
        if query:
            self._filtered_records = [
                record
                for record in self._records
                if query
                in " ".join(
                    str(record.get(field, ""))
                    for field in (
                        "name",
                        "payer_email",
                        "payer_phone",
                        "amount",
                        "received_at",
                    )
                ).casefold()
            ]
        else:
            self._filtered_records = list(self._records)
        self._page = 0
        self._render_rows()

    def _change_page(self, delta):
        page_count = max(
            1,
            (len(self._filtered_records) + HISTORY_PAGE_SIZE - 1)
            // HISTORY_PAGE_SIZE,
        )
        self._page = max(0, min(self._page + delta, page_count - 1))
        self._render_rows()

    def _render_rows(self):
        total = payment_history.total_amount(self._filtered_records)
        if self._history_error:
            summary = self._history_error
            self._summary.configure(text_color="#ef4444")
        elif len(self._filtered_records) == len(self._records):
            summary = f"{len(self._records)} payment(s)  •  Known total: ${total:,.2f}"
            self._summary.configure(text_color="#9ca3af")
        else:
            summary = (
                f"{len(self._filtered_records)} matching of {len(self._records)} payment(s)  "
                f"•  Known total: ${total:,.2f}"
            )
            self._summary.configure(text_color="#9ca3af")
        self._summary.configure(text=summary)

        page_count = max(
            1,
            (len(self._filtered_records) + HISTORY_PAGE_SIZE - 1)
            // HISTORY_PAGE_SIZE,
        )
        self._page = min(self._page, page_count - 1)
        start = self._page * HISTORY_PAGE_SIZE
        page_records = self._filtered_records[start : start + HISTORY_PAGE_SIZE]
        end = min(start + len(page_records), len(self._filtered_records))
        self._page_label.configure(
            text=(f"{start + 1}-{end} of {len(self._filtered_records)}" if end else "0 results")
        )
        self._previous_btn.configure(state="normal" if self._page else "disabled")
        self._next_btn.configure(
            state="normal" if self._page < page_count - 1 else "disabled"
        )

        children = self._rows.get_children()
        if children:
            self._rows.delete(*children)

        if not page_records:
            self._rows.insert(
                "",
                "end",
                values=(
                    "",
                    "No matching payments."
                    if self._records and self._search_var.get().strip()
                    else self._history_error or "No payments recorded yet.",
                    "",
                ),
            )
            return

        for record in page_records:
            self._rows.insert(
                "",
                "end",
                values=(
                    _format_history_date(record.get("received_at")),
                    _format_history_sender(record),
                    record.get("amount", "Unknown amount"),
                ),
            )

    def _load_backfill_state(self):
        state = payment_history.load_backfill_state()
        if not state or not state.get("gmail_account"):
            return state
        try:
            cfg = config.load() or {}
        except config.ConfigReadError:
            return state
        if state["gmail_account"] != cfg.get("gmail", "").strip().lower():
            return None
        return state

    def _update_backfill_controls(self):
        backfill_state = self._load_backfill_state()
        if backfill_state:
            saved_length = backfill_state.get("length", "1 year")
            self._backfill_length.set(saved_length)
            self._backfill_picker.configure(
                state="disabled" if saved_length == "Max" else "normal"
            )
            self._backfill_selection_changed()
            self._backfill_status.configure(
                text=(
                    "Completed once: "
                    f"{backfill_state.get('imported_count', 0)} payment(s) imported. "
                    "Choose a longer range to expand history, or rebuild this range."
                ),
                text_color="#22c55e",
            )
        elif not self._backfill_running:
            self._backfill_picker.configure(state="normal")
            self._backfill_btn.configure(state="normal", text="Import once")
            self._backfill_status.configure(
                text="Choose a range. You can expand or rebuild it later.",
                text_color="#9ca3af",
            )

    def _backfill_selection_changed(self, _value=None):
        backfill_state = self._load_backfill_state()
        if not backfill_state:
            self._backfill_btn.configure(text="Import once")
            return
        current = backfill_state.get("length", "1 year")
        selected = self._backfill_length.get()
        if BACKFILL_ORDER[selected] > BACKFILL_ORDER[current]:
            self._backfill_btn.configure(text="Expand history")
        else:
            self._backfill_btn.configure(text="Rebuild history")

    def _start_backfill(self):
        if self._backfill_running:
            self._backfill_cancel.set()
            self._backfill_btn.configure(state="disabled", text="Cancelling...")
            self._backfill_status.configure(
                text="Cancelling after the current Gmail request...",
                text_color="#f59e0b",
            )
            return
        backfill_state = self._load_backfill_state()
        selected_length = self._backfill_length.get()
        if backfill_state:
            current_length = backfill_state.get("length", "1 year")
            if BACKFILL_ORDER[selected_length] < BACKFILL_ORDER[current_length]:
                self._backfill_status.configure(
                    text=f"Choose {current_length} or a longer range.",
                    text_color="#f59e0b",
                )
                return
            self._backfill_mode = (
                "expand"
                if BACKFILL_ORDER[selected_length] > BACKFILL_ORDER[current_length]
                else "rebuild"
            )
            length = selected_length
        else:
            self._backfill_mode = "import"
            length = selected_length
        self._backfill_running = True
        self._backfill_cancel.clear()
        self._backfill_picker.configure(state="disabled")
        self._backfill_btn.configure(state="normal", text="Cancel")
        self._backfill_status.configure(
            text=(
                "Revalidating Gmail history. Existing imported records will be replaced..."
                if self._backfill_mode == "rebuild"
                else "Expanding history. This may take a while..."
                if self._backfill_mode == "expand"
                else "Scanning Gmail. This may take a while..."
            ),
            text_color="#f59e0b",
        )

        def run():
            def progress(scanned, total, validated):
                self.after(
                    0,
                    lambda: self._backfill_status.configure(
                        text=(
                            f"Scanned {scanned:,} of {total:,} Zelle-matching emails; "
                            f"validated {validated:,} payment(s)..."
                        ),
                        text_color="#f59e0b",
                    ),
                )

            try:
                matched_count, imported_count = self._on_backfill(
                    length,
                    self._backfill_mode in ("rebuild", "expand"),
                    progress,
                    self._backfill_cancel,
                )
            except Exception as exc:
                self.after(0, lambda: self._backfill_failed(str(exc)))
                return
            self.after(
                0,
                lambda: self._backfill_finished(matched_count, imported_count),
            )

        threading.Thread(target=run, daemon=True).start()

    def _backfill_finished(self, matched_count, imported_count):
        mode = self._backfill_mode
        self._backfill_running = False
        self.refresh()
        self._backfill_status.configure(
            text=(
                (
                    f"History rebuilt with {imported_count} validated payment(s)."
                    if mode == "rebuild"
                    else (
                        f"History expanded and rebuilt with {imported_count} "
                        "validated payment(s)."
                    )
                    if mode == "expand"
                    else (
                        f"Import complete: {imported_count} new payment(s) "
                        f"from {matched_count} matching email(s)."
                    )
                )
            ),
            text_color="#22c55e",
        )

    def _backfill_failed(self, message):
        self._backfill_running = False
        self._update_backfill_controls()
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

    def open_settings(self, on_save, existing_config=None, startup_error=None):
        if self._setup_win and self._setup_win.winfo_exists():
            self._setup_win.lift()
            self._setup_win.focus_force()
            return
        self._setup_win = SetupWindow(
            self,
            on_save=on_save,
            existing_config=existing_config,
            startup_error=startup_error,
        )

    def open_history(self, on_backfill):
        if self._history_win and self._history_win.winfo_exists():
            self._history_win.refresh()
            self._history_win.lift()
            self._history_win.focus_force()
            return
        self._history_win = HistoryWindow(self, on_backfill)
