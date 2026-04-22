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
