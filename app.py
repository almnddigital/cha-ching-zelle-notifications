"""
Cha-Ching Payment Notifications — Entry Point

Flow:
  1. Load saved config.
  2. If no config → show setup window.
  3. After setup (or if already configured) → start monitoring + show tray icon.
  4. App runs silently in the background until "Exit" is clicked from the tray.
"""

import logging
import os
import threading
from logging.handlers import RotatingFileHandler

import config
import gui
import monitor
import notify
import payment_history
import tray
import updates

# ── Logging ───────────────────────────────────────────────────────────────────
log_path = os.path.join(os.getenv("APPDATA", "."), "ChaChing", "monitor.log")
os.makedirs(os.path.dirname(log_path), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    handlers=[
        RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
    ],
)

# ── Globals ───────────────────────────────────────────────────────────────────
_app = None
_tray = None
_monitor = None
_update_prompted_version = None
_instance_mutex = None


# ── Callbacks ─────────────────────────────────────────────────────────────────

def _on_payment(
    name,
    amount,
    received_at=None,
    source_id=None,
    payer_email=None,
    payer_phone=None,
    is_test=False,
):
    logging.info("Validated payment received")
    payer = name or payer_email or payer_phone or "Unknown sender"
    if not is_test:
        try:
            inserted = payment_history.add_if_new(
                name,
                amount,
                received_at=received_at,
                source_id=source_id,
                payer_email=payer_email,
                payer_phone=payer_phone,
            )
        except Exception:
            logging.exception("Could not save payment history")
        else:
            if not inserted:
                logging.info("Duplicate payment notification suppressed")
                return
    notify.announce(payer, amount)
    if _app:
        _app.after(0, lambda: notify.show_popup(_app, payer, amount))


def _on_status(status):
    logging.info(f"STATUS: {status}")
    if _tray:
        _tray.set_status(status)


def _on_exit():
    if _monitor:
        _monitor.stop()
    if _app:
        _app.destroy()
    if _tray:
        _tray.stop()


def _start_monitoring(gmail, app_password, business_name=""):
    global _monitor
    logging.info("Starting Gmail monitor")
    if _monitor:
        _monitor.stop()
    _monitor = monitor.Monitor(
        gmail=gmail,
        app_password=app_password,
        on_payment=_on_payment,
        on_status=_on_status,
    )
    _monitor.start()


def _open_settings():
    if _app:
        startup_error = None
        try:
            cfg = config.load() or {}
        except config.ConfigReadError as exc:
            logging.exception("Could not load saved settings")
            cfg = {}
            startup_error = str(exc)
        _app.open_settings(
            on_save=lambda g, p, b: _start_monitoring(g, p, b),
            existing_config=cfg,
            startup_error=startup_error,
        )


def _open_history():
    if _app:
        _app.open_history(_run_backfill)


def _run_backfill(
    length,
    _replace_existing=False,
    on_progress=None,
    cancel_event=None,
):
    cfg = config.load() or {}
    if not cfg:
        raise RuntimeError("Configure Gmail before importing payment history.")
    try:
        records = monitor.fetch_historical_payments(
            cfg["gmail"],
            cfg["app_password"],
            length,
            on_progress=on_progress,
            cancel_event=cancel_event,
        )
        imported = payment_history.replace_gmail_records(records)
        payment_history.mark_backfill_complete(
            length,
            len(records),
            payment_history.gmail_record_count(),
            gmail_account=cfg["gmail"],
        )
        return len(records), imported
    except monitor.BackfillCancelled:
        raise
    except Exception:
        logging.exception("Gmail payment history backfill failed")
        raise RuntimeError("Could not import Gmail payments. Check Settings and try again.")


def _install_update(release):
    try:
        updates.install_update(release)
    except Exception:
        logging.exception("Could not start Cha-Ching update")
        if _app:
            _app.after(0, lambda: notify.show_update_error(_app))
        return
    _on_exit()


def _check_for_updates(manual=False):
    def run():
        global _update_prompted_version
        try:
            release = updates.check_for_update()
        except Exception:
            logging.exception("Could not check for Cha-Ching updates")
            if manual and _app:
                _app.after(
                    0,
                    lambda: notify.show_update_status(
                        _app,
                        "Update Check Failed",
                        "Could not reach GitHub. Your current version was not changed.",
                        is_error=True,
                    ),
                )
            return
        if not release:
            if manual and _app:
                _app.after(
                    0,
                    lambda: notify.show_update_status(
                        _app,
                        "You're Up to Date",
                        "This is the latest available version of Cha-Ching.",
                    ),
                )
            return
        if release["version"] == _update_prompted_version and not manual:
            return
        _update_prompted_version = release["version"]
        if _app:
            _app.after(
                0,
                lambda: notify.show_update_popup(
                    _app,
                    release["version"],
                    lambda: _install_update(release),
                ),
            )

    threading.Thread(target=run, daemon=True).start()


# ── Boot ──────────────────────────────────────────────────────────────────────

def main():
    global _app, _tray, _instance_mutex

    if os.name == "nt":
        import win32api
        import win32event
        import winerror

        _instance_mutex = win32event.CreateMutex(None, False, "Local\\ChaChingPaymentNotifications")
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                0,
                "Cha-Ching is already running in the system tray.",
                "Cha-Ching",
                0x40,
            )
            return

    _app = gui.App()

    _tray = tray.Tray(
        on_open_settings=lambda: _app.after(0, _open_settings),
        on_open_history=lambda: _app.after(0, _open_history),
        on_test=lambda: _app.after(
            0,
            lambda: _on_payment("Maria", "$45.00", is_test=True),
        ),
        on_check_updates=lambda: _app.after(0, lambda: _check_for_updates(manual=True)),
        on_exit=lambda: _app.after(0, _on_exit),
    )
    _tray.start()

    try:
        cfg = config.load()
    except config.ConfigReadError:
        logging.exception("Could not load saved settings")
        cfg = None

    if cfg:
        _start_monitoring(cfg["gmail"], cfg["app_password"])
    else:
        _app.after(200, _open_settings)
    _app.after(3000, _check_for_updates)

    _app.mainloop()


if __name__ == "__main__":
    main()
