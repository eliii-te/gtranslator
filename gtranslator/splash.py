"""gtranslator splash — modern, animated, centered, short.

Frameless dark panel with a custom-drawn rotating ring spinner
(no legacy ttk widgets). Shows for at least MIN_SHOW_SECONDS and
closes as soon as the app window appears (or the worker finishes),
hard-capped at MAX_SHOW_SECONDS. destroy() runs in a finally block,
so the splash can never linger.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time

MIN_SHOW_SECONDS = 2.0
MAX_SHOW_SECONDS = 15.0

BG = "#0b0e14"
FG_DIM = "#6b7280"
FG_TEXT = "#e5e7eb"
ACCENT = "#34d399"
RING_TRACK = "#1c2530"


def _window_seen(app_display: str) -> bool:
    xdotool = shutil.which("xdotool")
    if not xdotool:
        return False
    try:
        env = dict(os.environ, DISPLAY=app_display)
        out = subprocess.run(
            [xdotool, "search", "--onlyvisible", "--name", "."],
            capture_output=True, text=True, env=env, timeout=5,
        ).stdout.split()
        return len(out) > 1
    except Exception:
        return False


def wait_for_window_or_stop(app_display: str, stop: threading.Event) -> None:
    """Poll the app display; set stop when an app window appears."""
    deadline = time.time() + MAX_SHOW_SECONDS
    while time.time() < deadline and not stop.is_set():
        if _window_seen(app_display):
            stop.set()
            return
        time.sleep(0.25)


def show_splash_blocking(app_name: str, stop: threading.Event) -> None:
    """Blocking animated splash (ring spinner). Returns once the app
    window is up and the minimum time passed, or at the max time.
    Never raises; console fallback when headless. Always destroys the
    window, even on errors."""
    if not os.environ.get("DISPLAY"):
        print(f"gtranslator™: starting {app_name} …")
        return
    try:
        import tkinter as tk
    except ImportError:
        print(f"gtranslator™: starting {app_name} …")
        return

    root = None
    try:
        start = time.time()
        root = tk.Tk()
        root.title("gtranslator™")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=BG)

        w, h = 560, 200
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

        tk.Label(
            root, text="gtranslator™", bg=BG, fg=ACCENT,
            font=("Sans", 27, "bold"),
        ).pack(pady=(24, 0))
        tk.Label(
            root, text=f"starting {app_name}", bg=BG, fg=FG_TEXT,
            font=("Sans", 13),
        ).pack(pady=(2, 0))
        tk.Label(
            root, text="winsecure™ bubble · isolated · no host access",
            bg=BG, fg=FG_DIM, font=("Sans", 9),
        ).pack(pady=(2, 10))

        size = 56
        canvas = tk.Canvas(
            root, width=size, height=size, bg=BG, highlightthickness=0
        )
        canvas.pack(pady=(2, 6))
        cx = cy = size / 2
        r = size / 2 - 5
        canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r, outline=RING_TRACK, width=4
        )
        arc = canvas.create_arc(
            cx - r, cy - r, cx + r, cy + r,
            start=0, extent=100, outline=ACCENT, width=4, style="arc",
        )
        root.update()

        angle = 0
        while not (stop.is_set() and time.time() - start >= MIN_SHOW_SECONDS):
            if time.time() - start >= MAX_SHOW_SECONDS:
                break
            angle = (angle + 9) % 360
            canvas.itemconfigure(arc, start=angle)
            root.update()
            time.sleep(0.016)
    except Exception:
        pass
    finally:
        if root is not None:
            try:
                root.destroy()
            except Exception:
                pass
