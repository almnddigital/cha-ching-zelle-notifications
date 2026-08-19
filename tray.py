"""
System tray icon — runs in a background thread via pystray.
Shows connection status via color-coded bell icon and provides quick-access menu.
"""

import threading

import pystray
from PIL import Image, ImageDraw


def _make_icon(color):
    """Draw a simple bell-shaped icon in the given color."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([12, 8, 52, 48], fill=color)
    d.rectangle([12, 28, 52, 48], fill=color)
    d.ellipse([26, 46, 38, 58], fill=color)
    d.rectangle([28, 4, 36, 14], fill=color)
    return img


ICONS = {
    "connected": _make_icon("#22c55e"),      # green
    "connecting": _make_icon("#f59e0b"),      # amber
    "reconnecting": _make_icon("#f59e0b"),    # amber
    "stopped": _make_icon("#6b7280"),         # gray
    "error": _make_icon("#ef4444"),           # red
}


class Tray:
    def __init__(self, on_open_settings, on_open_history, on_test, on_exit):
        self.on_open_settings = on_open_settings
        self.on_open_history = on_open_history
        self.on_test = on_test
        self.on_exit = on_exit
        self._icon = None

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Cha-Ching Payment Notifications", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Settings", lambda: self.on_open_settings()),
            pystray.MenuItem("Payment History", lambda: self.on_open_history()),
            pystray.MenuItem("Send Test Announcement", lambda: self.on_test()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda: self._do_exit()),
        )

    def _do_exit(self):
        self.on_exit()
        if self._icon:
            self._icon.stop()

    def start(self):
        self._icon = pystray.Icon(
            "ChaChing",
            ICONS["connecting"],
            "Cha-Ching Payment Notifications — Connecting…",
            self._build_menu(),
        )
        threading.Thread(target=self._icon.run, daemon=True).start()

    def set_status(self, status):
        if not self._icon:
            return
        titles = {
            "connected": "Cha-Ching Payment Notifications — Listening",
            "connecting": "Cha-Ching Payment Notifications — Connecting…",
            "reconnecting": "Cha-Ching Payment Notifications — Reconnecting…",
            "stopped": "Cha-Ching Payment Notifications — Stopped",
        }
        self._icon.icon = ICONS.get(status, ICONS["connecting"])
        self._icon.title = titles.get(status, "Cha-Ching Payment Notifications")

    def stop(self):
        if self._icon:
            self._icon.stop()
