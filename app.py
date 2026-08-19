"""
Cha-Ching Payment Notifications — Entry Point

Flow:
  1. Load saved config.
  2. If no config → show setup window.
  3. After setup (or if already configured) → start monitoring + show tray icon.
  4. App runs silently in the background until "Exit" is clicked from the tray.
"""

import sys
import logging
import os
import threading

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
    filename=log_path,
    level=logging.INFO,
    format="%(asctime)s %(message)s",
)

# ── Globals ───────────────────────────────────────────────────────────────────
_app = None
_tray = None
_monitor = None
_update_prompted_version = None


# ── Callbacks ─────────────────────────────────────────────────────────────────

def _on_payment(
    name,
    amount,
    received_at=None,
    source_id=None,
    sender_email=None,
    is_test=False,
):
    logging.info(f"PAYMENT TRIGGERED: name={name} amount={amount}")
    if not is_test:
        try:
            payment_history.add(
                name,
                amount,
                received_at=received_at,
                source_id=source_id,
                sender_email=sender_email,
            )
        except Exception:
            logging.exception("Could not save payment history")
    notify.announce(name, amount)
    if _app:
        _app.after(0, lambda: notify.show_popup(_app, name, amount))


def _on_status(status):
    logging.info(f"STATUS: {status}")
    if _tray:
        _tray.set_status(status)


def _on_exit():
    if _monitor:
        _monitor.stop()
    if _app:
        _app.quit()
    sys.exit(0)


def _start_monitoring(gmail, app_password, business_name=""):
    global _monitor
    logging.info(f"Starting monitor for {gmail}")
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
        cfg = config.load() or {}
        _app.open_settings(
            on_save=lambda g, p, b: _start_monitoring(g, p, b),
            existing_config=cfg,
        )


def _open_history():
    if _app:
        _app.open_history(_run_backfill)


def _run_backfill(length):
    cfg = config.load() or {}
    if not cfg:
        raise RuntimeError("Configure Gmail before importing payment history.")
    try:
        records = monitor.fetch_historical_payments(
            cfg["gmail"],
            cfg["app_password"],
            length,
        )
        imported = sum(
            payment_history.add_if_new(
                record["name"],
                record["amount"],
                received_at=record["received_at"],
                source_id=record["source_id"],
                sender_email=record.get("sender_email"),
            )
            for record in records
        )
        payment_history.mark_backfill_complete(length, len(records), imported)
        return len(records), imported
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


def _check_for_updates():
    def run():
        global _update_prompted_version
        try:
            release = updates.check_for_update()
        except Exception:
            logging.exception("Could not check for Cha-Ching updates")
            return
        if not release or release["version"] == _update_prompted_version:
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
    global _app, _tray

    _app = gui.App()

    _tray = tray.Tray(
        on_open_settings=_open_settings,
        on_open_history=_open_history,
        on_test=lambda: _on_payment("Maria", "$45.00", is_test=True),
        on_exit=_on_exit,
    )
    _tray.start()

    cfg = config.load()

    if cfg:
        _start_monitoring(cfg["gmail"], cfg["app_password"])
    else:
        _app.after(200, _open_settings)
    _app.after(3000, _check_for_updates)

    _app.mainloop()


if __name__ == "__main__":
    main()
