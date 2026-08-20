"""
Audio + visual notifications — ka-ching sound, text-to-speech,
and persistent popup window.

Uses Windows built-in Speech API (SAPI5) via pyttsx3 and winsound.Beep
for the ka-ching effect. No internet required.
"""

import os
import sys
import threading
import winsound

import pyttsx3
import customtkinter as ctk

_open_popups = []
_update_popup = None


def _resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


_KACHING_WAV = _resource_path("chachingsound.wav")


def _kaching():
    winsound.PlaySound(_KACHING_WAV, winsound.SND_FILENAME)


def _speak(text):
    engine = pyttsx3.init()
    engine.setProperty("rate", 145)
    voices = engine.getProperty("voices")
    if len(voices) > 1:
        engine.setProperty("voice", voices[1].id)
    engine.say(text)
    engine.runAndWait()


def announce(name, amount):
    """Play ka-ching chime then speak the announcement in a background thread."""
    if name and amount:
        text = f"Payment of {amount} received from {name}."
    elif amount:
        text = f"Payment of {amount} received."
    else:
        text = "Zelle payment received."

    def _run():
        _kaching()
        _speak(text)

    threading.Thread(target=_run, daemon=True).start()


def show_popup(master, name, amount):
    """Show a persistent bottom-right popup that stacks above previous ones."""
    popup = ctk.CTkToplevel(master)
    popup.title("")
    popup.resizable(False, False)
    popup.attributes("-topmost", True)

    w = 360
    sw = master.winfo_screenwidth()
    sh = master.winfo_screenheight()

    ctk.CTkFrame(popup, fg_color="#16a34a", height=8, corner_radius=0).pack(fill="x")
    ctk.CTkLabel(
        popup,
        text="Zelle Payment Received",
        font=ctk.CTkFont(size=15, weight="bold"),
    ).pack(pady=(16, 4))

    if name and amount:
        detail = f"{amount}  from  {name}"
    elif amount:
        detail = amount
    else:
        detail = "Payment confirmed"

    ctk.CTkLabel(
        popup,
        text=detail,
        font=ctk.CTkFont(size=17, weight="bold"),
        text_color="#22c55e",
        wraplength=300,
        justify="center",
    ).pack(pady=(0, 16), padx=20)

    info = {"height": 0}

    def on_dismiss():
        _open_popups.remove(info)
        popup.destroy()

    ctk.CTkButton(
        popup,
        text="TAP TO DISMISS",
        height=50,
        font=ctk.CTkFont(size=14, weight="bold"),
        fg_color="#16a34a",
        hover_color="#15803d",
        command=on_dismiss,
    ).pack(fill="x", padx=20, pady=(0, 20))

    popup.update_idletasks()
    h = popup.winfo_reqheight()
    info["height"] = h

    # Stack above existing popups
    stack_offset = sum(p["height"] + 10 for p in _open_popups)
    x = sw - w - 20
    y = sh - h - 70 - stack_offset
    popup.geometry(f"{w}x{h}+{x}+{y}")

    _open_popups.append(info)


def test_announcement():
    """Demo announcement for the tray menu test button."""
    announce("Maria", "$45.00")


def show_update_popup(master, version, on_update):
    global _update_popup
    if _update_popup and _update_popup.winfo_exists():
        _update_popup.lift()
        _update_popup.focus_force()
        return

    popup = ctk.CTkToplevel(master)
    _update_popup = popup
    popup.title("Cha-Ching Update Available")
    popup.resizable(False, False)
    popup.attributes("-topmost", True)
    popup.geometry("440x240")

    ctk.CTkFrame(popup, fg_color="#2563eb", height=8, corner_radius=0).pack(fill="x")
    ctk.CTkLabel(
        popup,
        text="A new version is ready",
        font=ctk.CTkFont(size=18, weight="bold"),
    ).pack(pady=(22, 4))
    ctk.CTkLabel(
        popup,
        text=f"Cha-Ching {version} is available.\nUpdate now to keep the app current?",
        text_color="#d1d5db",
        justify="center",
    ).pack(pady=(0, 18))

    buttons = ctk.CTkFrame(popup, fg_color="transparent")
    buttons.pack(fill="x", padx=24, pady=(0, 22))

    def dismiss():
        global _update_popup
        _update_popup = None
        popup.destroy()

    def update():
        update_button.configure(state="disabled", text="Updating...")
        later_button.configure(state="disabled")
        popup.after(100, lambda: (dismiss(), on_update()))

    later_button = ctk.CTkButton(
        buttons,
        text="Later",
        width=120,
        fg_color="#374151",
        hover_color="#4b5563",
        command=dismiss,
    )
    later_button.pack(side="left")
    update_button = ctk.CTkButton(
        buttons,
        text="Update now",
        width=160,
        fg_color="#2563eb",
        hover_color="#1d4ed8",
        command=update,
    )
    update_button.pack(side="right")


def show_update_error(master):
    popup = ctk.CTkToplevel(master)
    popup.title("Update Failed")
    popup.resizable(False, False)
    popup.attributes("-topmost", True)
    popup.geometry("420x190")
    ctk.CTkLabel(
        popup,
        text="The update could not be started.",
        font=ctk.CTkFont(size=16, weight="bold"),
    ).pack(pady=(28, 10))
    ctk.CTkLabel(
        popup,
        text="The current app is still installed. Please try again later.",
        text_color="#d1d5db",
    ).pack(pady=(0, 20))
    ctk.CTkButton(popup, text="Close", width=120, command=popup.destroy).pack()


def show_update_status(master, title, message, is_error=False):
    popup = ctk.CTkToplevel(master)
    popup.title(title)
    popup.resizable(False, False)
    popup.attributes("-topmost", True)
    popup.geometry("420x190")
    ctk.CTkLabel(
        popup,
        text=title,
        font=ctk.CTkFont(size=16, weight="bold"),
        text_color="#ef4444" if is_error else "#22c55e",
    ).pack(pady=(28, 10))
    ctk.CTkLabel(
        popup,
        text=message,
        text_color="#d1d5db",
        wraplength=360,
        justify="center",
    ).pack(pady=(0, 20))
    ctk.CTkButton(popup, text="Close", width=120, command=popup.destroy).pack()
