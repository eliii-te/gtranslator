"""gtranslator splash — "starting with gtranslator™".

Runs as a *separate process* on the host display so it can never block
or crash the launcher. It closes itself when the app's first window
appears on the isolated display (polled via xdotool) or after a timeout.

Usage (internal):
    python3 -m gtranslator.splash "<app name>" "<isolated display>"
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time

SPLASH_SECONDS = 25


def _poll_until_window(isolated_display: str, stop: threading.Event) -> None:
    xdotool = shutil.which("xdotool")
    deadline = time.time() + SPLASH_SECONDS
    while time.time() < deadline and not stop.is_set():
        if xdotool:
            try:
                env = dict(os.environ, DISPLAY=isolated_display)
                out = subprocess.run(
                    [xdotool, "search", "--onlyvisible", "--name", "."],
                    capture_output=True, text=True, env=env, timeout=5,
                ).stdout.split()
                # more than the root window id → an app window is mapped
                if len(out) > 1:
                    break
            except Exception:
                pass
        time.sleep(0.5)
    stop.set()


def _run_splash(app_name: str, isolated_display: str) -> None:
    try:
        import tkinter as tk
    except ImportError:
        return
    try:
        root = tk.Tk()
        root.title("gtranslator™")
        root.attributes("-topmost", True)
        root.configure(bg="#0f1115")
        w, h = 520, 170
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")
        tk.Label(
            root, text="gtranslator™", bg="#0f1115", fg="#6ee7b7",
            font=("Sans", 22, "bold"),
        ).pack(pady=(26, 0))
        tk.Label(
            root, text=f"starting {app_name} …",
            bg="#0f1115", fg="#e5e7eb", font=("Sans", 13),
        ).pack(pady=(8, 0))
        tk.Label(
            root, text="winsecure™ bubble · isolated · no host access",
            bg="#0f1115", fg="#6b7280", font=("Sans", 9),
        ).pack(pady=(4, 0))
        root.update()

        stop = threading.Event()
        poller = threading.Thread(
            target=_poll_until_window, args=(isolated_display, stop),
            daemon=True,
        )
        poller.start()
        # keep tk pumping until the poller says an app window appeared
        while not stop.is_set():
            root.update()
            time.sleep(0.05)
        root.destroy()
    except Exception:
        pass


def start_splash_process(app_name: str, isolated_display: str) -> subprocess.Popen:
    """Launch the splash as its own process; returns the Popen handle."""
    code = os.path.dirname(os.path.abspath(__file__))
    project = os.path.dirname(code)
    env = dict(os.environ)
    env.setdefault("PYTHONPATH", project)
    return subprocess.Popen(
        [sys.executable, "-m", "gtranslator.splash", app_name, isolated_display],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_splash_process(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else "application"
    display = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("DISPLAY", ":0")
    _run_splash(name, display)
