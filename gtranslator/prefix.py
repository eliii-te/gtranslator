"""gtranslator prefix management — isolated Wine prefixes per app.

Every Windows app gets its own WINEPREFIX under the gtranslator data
dir. Prefixes live inside the winsecure™ bubble and are never exposed
to the host filesystem layout.

Installed programs (from installers) live *inside* their prefix at
drive_c/… and are started from there; portable apps are stored in the
.gwp container and extracted to a per-app exe cache at run time.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import time

from . import sandbox

CREATED_MARKER = ".gtranslator-created"


def app_id(exe_path: str) -> str:
    """Stable, readable id for an .exe: name + short hash."""
    name = os.path.splitext(os.path.basename(exe_path))[0]
    name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
    digest = hashlib.sha256(os.path.abspath(exe_path).encode()).hexdigest()[:8]
    return f"{name}-{digest}"


def _base_dir(aid: str) -> str:
    return os.path.join(sandbox.DATA_HOME, "apps", aid)


def paths_for_id(aid: str) -> dict:
    base = _base_dir(aid)
    return {
        "id": aid,
        "base": base,
        "prefix": os.path.join(base, "wineprefix"),
        "home": os.path.join(base, "home"),
        "exe_cache": os.path.join(base, "exe"),
    }


def ensure_dirs(aid: str) -> dict:
    paths = paths_for_id(aid)
    for key in ("base", "prefix", "home", "exe_cache"):
        os.makedirs(paths[key], exist_ok=True)
    return paths


def ensure_wineboot(bubble: sandbox.Bubble) -> None:
    """Run wineboot inside the bubble to (re)initialise the prefix.

    Runs *headless* (no X display): prefix initialisation must never
    depend on the isolated display — explorer startup with X can hang
    during first boot. Only the actual application gets the display.
    """
    headless = sandbox.Bubble(
        display=None,
        prefix=bubble.prefix,
        app_home=bubble.app_home,
        exe_host_path=None,
        exe_bubble_path=None,
        arch=bubble.arch,
        network=bubble.network,
        env=bubble.env,
    )
    subprocess.run(headless.build(["wineboot", "-u"]), check=False, timeout=300)
    marker = os.path.join(bubble.prefix, CREATED_MARKER)
    if not os.path.exists(marker):
        with open(marker, "w") as fh:
            fh.write(str(time.time()))


def prefix_created_ts(prefix_dir: str) -> float:
    """Timestamp of prefix creation (for installer discovery)."""
    marker = os.path.join(prefix_dir, CREATED_MARKER)
    if os.path.exists(marker):
        try:
            return float(open(marker).read().strip())
        except (OSError, ValueError):
            pass
    reg = os.path.join(prefix_dir, "system.reg")
    if os.path.exists(reg):
        return os.path.getmtime(reg)
    return time.time()


def discover_installed_exe(prefix_dir: str, limit: int = 8) -> list[str]:
    """Find freshly installed .exe files after an installer ran.

    Scans Program Files / AppData program dirs inside the prefix for
    executables newer than the prefix creation. Returns host-side paths
    (inside the prefix dir) sorted by size, biggest first.
    """
    created = prefix_created_ts(prefix_dir)
    roots = [
        os.path.join(prefix_dir, "drive_c", "Program Files"),
        os.path.join(prefix_dir, "drive_c", "Program Files (x86)"),
        os.path.join(prefix_dir, "drive_c", "Users"),
    ]
    candidates: list[tuple[str, float]] = []
    seen = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                if not fn.lower().endswith(".exe"):
                    continue
                full = os.path.join(dirpath, fn)
                try:
                    mtime = os.path.getmtime(full)
                except OSError:
                    continue
                # ignore things inside obviously non-app dirs
                low = full.lower()
                if any(
                    seg in low
                    for seg in ("\\temp", "/temp", "\\cache", "/cache",
                                "microsoft", "windows kits", "installer")
                ):
                    continue
                if mtime >= created - 120 and full not in seen:
                    seen.add(full)
                    candidates.append((full, os.path.getsize(full)))
    candidates.sort(key=lambda c: c[1], reverse=True)
    return [c[0] for c in candidates[:limit]]


def list_prefixes() -> list[dict]:
    apps_dir = os.path.join(sandbox.DATA_HOME, "apps")
    result = []
    if not os.path.isdir(apps_dir):
        return result
    for aid in sorted(os.listdir(apps_dir)):
        base = os.path.join(apps_dir, aid)
        if os.path.isdir(base):
            size = 0
            for root, _dirs, files in os.walk(base):
                for f in files:
                    try:
                        size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            result.append({"id": aid, "dir": base, "size": size})
    return result


def remove_prefix(aid: str) -> bool:
    base = _base_dir(aid)
    if not os.path.isdir(base):
        return False
    shutil.rmtree(base, ignore_errors=True)
    return True


def human_size(num: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if num < 1024 or unit == "G":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} G"
