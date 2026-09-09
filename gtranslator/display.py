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


def host_monitor_size() -> tuple[int, int] | None:
    """Return (width, height) of the active Hyprland monitor, if any.

    Used to size the isolated Xephyr display so the Windows app can
    run fullscreen 1:1 with the host screen.
    """
    try:
        sig_dir = f"/run/user/{os.getuid()}/hypr"
        sigs = [d for d in os.listdir(sig_dir)
                if os.path.isdir(os.path.join(sig_dir, d))]
        if not sigs:
            return None
        import json

        env = dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE=sigs[0])
        out = subprocess.run(
            ["hyprctl", "-j", "monitors"], env=env,
            capture_output=True, text=True, timeout=5,
        ).stdout
        monitors = json.loads(out)
        if not monitors:
            return None
        m = monitors[0]
        return int(m.get("width")), int(m.get("height"))
    except Exception:
        return None


def _hyprctl(args: list[str]) -> str:
    """Run hyprctl against the user's running Hyprland instance."""
    try:
        sig_dir = f"/run/user/{os.getuid()}/hypr"
        sigs = [d for d in os.listdir(sig_dir)
                if os.path.isdir(os.path.join(sig_dir, d))]
        if not sigs:
            return ""
        env = dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE=sigs[0])
        return subprocess.run(
            ["hyprctl", *args], env=env,
            capture_output=True, text=True, timeout=5,
        ).stdout
    except Exception:
        return ""


def hyprland_prepare() -> None:
    """Set runtime window rules before the Xephyr window maps.

    Hyprland 0.56 refuses to tile Xephyr windows (it always floats
    them, even with float-off rules). What works: centering via a
    runtime keyword rule — the window then appears centered and
    focused like a normal app window instead of at 0,0.
    """
    _hyprctl(["keyword", "windowrule",
              "match:class ^(Xephyr)$, center on"])
    _hyprctl(["keyword", "windowrule",
              "match:class ^(Xephyr)$, focus on"])


def hyprland_focus(class_pattern: str = "Xephyr") -> None:
    """Make the app window behave like a normal host window.

    Hyprland floats Xephyr windows by default; we actively un-float
    (tile) it and pull it into focus so it joins the window layout.
    Uses the concrete window address (deterministic) instead of
    class-pattern dispatches. Non-invasive: hyprctl runtime only.
    """
    try:
        import json

        clients = _hyprctl(["-j", "clients"])
        if not clients:
            return
        windows = [
            c for c in json.loads(clients)
            if c.get("class") == class_pattern
        ]
        for c in windows:
            addr = c.get("address", "")
            if not addr:
                continue
            if c.get("floating"):
                _hyprctl(["dispatch", "setfloating", f"address:{addr}"])
                import time

                time.sleep(0.4)
            _hyprctl(["dispatch", "focuswindow", f"address:{addr}"])
    except Exception:
        pass


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
