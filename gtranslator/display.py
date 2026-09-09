"""gtranslator display isolation — Xephyr on a private X display.

The Windows app never touches GlassyOS's own display/compositor.
It renders into a nested X server (Xephyr) on its own display number,
which the host shows as a normal window.

If the host is Wayland-only, Xephyr needs XWayland to be available
(standard on GlassyOS / Hyprland).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time

DISPLAY_START = 90  # high display numbers to avoid collisions
DISPLAY_END = 120


def find_free_display() -> str | None:
    """Pick the first unused X display number >= DISPLAY_START."""
    for num in range(DISPLAY_START, DISPLAY_END):
        if not os.path.exists(f"/tmp/.X11-unix/X{num}"):
            return f":{num}"
    return None


def require_xephyr() -> str | None:
    return shutil.which("Xephyr")


class XephyrServer:
    """Lifecycle of one isolated X server."""

    def __init__(
        self,
        title: str = "gtranslator™",
        geometry: str = "1280x800x24",
    ):
        self.display = find_free_display()
        if self.display is None:
            raise RuntimeError("no free display slot found")
        self.title = title
        self.geometry = geometry
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        xephyr = require_xephyr()
        if xephyr is None:
            raise RuntimeError(
                "Xephyr not installed — needed for the isolated display. "
                "Install: sudo pacman -S xorg-server-xephyr"
            )
        if not os.environ.get("DISPLAY"):
            raise RuntimeError(
                "no host display found (DISPLAY is unset) — gtranslator "
                "must run from a desktop session"
            )
        self.proc = subprocess.Popen(
            [
                xephyr,
                self.display,
                "-ac",            # disable access control (bubble has no auth)
                "-screen", self.geometry,
                "-title", self.title,
                "-noreset",
                "-nolisten", "tcp",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Wait until the socket appears.
        sock = f"/tmp/.X11-unix/X{self.display.lstrip(':')}"
        for _ in range(50):
            if os.path.exists(sock):
                return
            if self.proc.poll() is not None:
                raise RuntimeError("Xephyr exited during startup")
            time.sleep(0.1)
        raise RuntimeError("Xephyr socket never appeared")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
