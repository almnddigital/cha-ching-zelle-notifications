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

import config
import gui
import monitor
import notify
import tray

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


# ── Callbacks ─────────────────────────────────────────────────────────────────

def _on_payment(name, amount):
    logging.info(f"PAYMENT TRIGGERED: name={name} amount={amount}")
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


# ── Boot ──────────────────────────────────────────────────────────────────────

def main():
    global _app, _tray

    _app = gui.App()

    _tray = tray.Tray(
        on_open_settings=_open_settings,
        on_test=lambda: _on_payment("Maria", "$45.00"),
        on_exit=_on_exit,
    )
    _tray.start()

    cfg = config.load()

    if cfg:
        _start_monitoring(cfg["gmail"], cfg["app_password"])
    else:
        _app.after(200, _open_settings)

    _app.mainloop()


if __name__ == "__main__":
    main()
