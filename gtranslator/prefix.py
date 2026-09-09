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
SNAPSHOT_FILE = ".exe-snapshot"

# Wine's own programs — never real apps the user installed.
WINE_BUILTIN_DIRS = {
    "windows nt", "internet explorer", "windows media player",
    "common files", "windows photo viewer", "windows portable devices",
    "mozilla maintenance service",
}
WINE_BUILTIN_TOP = {"windows", "syswow64", "program files",
                     "program files (x86)"}


def _iter_exes(prefix_dir: str):
    """Yield relative (to prefix_dir) paths of .exe files under drive_c
    that could be user-installed programs."""
    drive_c = os.path.join(prefix_dir, "drive_c")
    if not os.path.isdir(drive_c):
        return
    for dirpath, _dirnames, filenames in os.walk(drive_c):
        for fn in filenames:
            if not fn.lower().endswith(".exe"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, prefix_dir)
            rel_low = rel.lower().replace("/", os.sep)
            parts = rel_low.split(os.sep)
            # drive_c\windows\… and friends are never apps
            if len(parts) > 1 and parts[1] in ("windows", "syswow64"):
                continue
            low = rel_low
            if any(
                os.sep + b + os.sep in os.sep + low + os.sep
                for b in WINE_BUILTIN_DIRS
            ):
                continue
            # only the top-level program dirs + drive_c root folders
            if len(parts) > 2 and parts[1] in WINE_BUILTIN_TOP:
                # allow Program Files/<Vendor>/app.exe, but not deeper
                # builtin trees already filtered above
                pass
            yield rel


def _write_snapshot(prefix_dir: str) -> None:
    """Snapshot of all exe files right after prefix init."""
    exes = sorted(_iter_exes(prefix_dir))
    with open(os.path.join(prefix_dir, SNAPSHOT_FILE), "w") as fh:
        fh.write("\n".join(exes))


def _read_snapshot(prefix_dir: str) -> set[str]:
    path = os.path.join(prefix_dir, SNAPSHOT_FILE)
    if not os.path.exists(path):
        return set()
    try:
        with open(path) as fh:
            return {line.strip() for line in fh if line.strip()}
    except OSError:
        return set()


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
    After init, registry values pretend a modern Windows so installers
    don't demand "update your Windows" (Chromium setups do this).
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
    marker = os.path.join(bubble.prefix, CREATED_MARKER)
    if not os.path.exists(marker):
        subprocess.run(headless.build(["wineboot", "-u"]), check=False, timeout=300)
        _pretend_modern_windows(headless)
        _write_snapshot(bubble.prefix)
        with open(marker, "w") as fh:
            fh.write(str(time.time()))
    elif not os.path.exists(os.path.join(bubble.prefix, SNAPSHOT_FILE)):
        # legacy prefix without snapshot: baseline it now
        _write_snapshot(bubble.prefix)


# Values pretending a modern, fully-updated Windows 11 install. Many
# installers (Edge/Chrome-family) refuse to run on "outdated" systems.
_WINVER_KEY = r"HKLM\Software\Microsoft\Windows NT\CurrentVersion"
_WINVER_VALUES = [
    ("ProductName", "Windows 11 Pro"),
    ("CurrentVersion", "10.0"),
    ("CurrentBuild", "22631"),
    ("CurrentBuildNumber", "22631"),
    ("UBR", "4036"),
    ("EditionID", "Professional"),
    ("DisplayVersion", "23H2"),
    ("BuildLabEx", "22631.4036.amd64fre.ni_release.230000-0000"),
]


def _pretend_modern_windows(headless: sandbox.Bubble) -> None:
    """Set registry version values inside the prefix via wine reg add.

    All adds run in ONE bubble instance and end with `wineserver -k`
    so the registry cache is flushed — separate instances would hard-
    kill the wineserver and silently lose every change.
    """
    cmds = " && ".join(
        f'wine reg add "{_WINVER_KEY}" /v {name} /d "{value}" /f'
        for name, value in _WINVER_VALUES
    )
    cmds += " && wineserver -k"
    subprocess.run(
        headless.build(["/bin/sh", "-c", cmds]),
        check=False, timeout=240,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


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
    """Find .exe files that appeared since prefix initialisation.

    Snapshot-based: everything not in the post-wineboot snapshot is a
    candidate (installers set archive timestamps, so mtime is useless).
    Returns host-side paths sorted by size, biggest first.
    """
    snapshot = _read_snapshot(prefix_dir)
    if not snapshot:
        # legacy/best-effort: snapshot now — nothing before this point
        # counts as newly installed
        _write_snapshot(prefix_dir)
        return []
    current = set(_iter_exes(prefix_dir))
    fresh = current - snapshot
    candidates = []
    for rel in fresh:
        full = os.path.join(prefix_dir, rel)
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        # main-app heuristic: exe name appears in its folder name
        # (firefox.exe in "Mozilla Firefox") → rank first
        parent = os.path.basename(os.path.dirname(full)).lower()
        stem = os.path.splitext(os.path.basename(full))[0].lower()
        main = 0 if stem and stem in parent else 1
        candidates.append((full, size, main))
    candidates.sort(key=lambda c: (c[2], -c[1]))
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


# ---------------------------------------------------------------------------
# visible user-data folder (~/gtranslator/<App> with Windows layout)
# ---------------------------------------------------------------------------

# Windows user profile layout, recreated on the host so the user can
# browse exactly what their Windows apps write.
USERDATA_SUBDIRS = [
    "AppData/Local",
    "AppData/Roaming",
    "AppData/LocalLow",
    "Desktop",
    "Documents",
    "Downloads",
    "Music",
    "Pictures",
    "Videos",
]


def userdata_root() -> str:
    return os.path.join(os.path.expanduser("~"), "gtranslator")


def wine_user_name(prefix_dir: str) -> str | None:
    """Name of the windows user inside the prefix (C:/users/<name>)."""
    users = os.path.join(prefix_dir, "drive_c", "users")
    if not os.path.isdir(users):
        return None
    for entry in sorted(os.listdir(users)):
        if entry.lower() not in ("public", "default", "all users", "default user"):
            return entry
    return None


def prepare_userdata(app_name: str, prefix_dir: str) -> str | None:
    """Create ~/gtranslator/<App> with the Windows profile layout and
    migrate any existing prefix user data into it. Returns the host
    dir (or None if no wine user exists yet)."""
    user = wine_user_name(prefix_dir)
    if not user:
        return None
    safe = "".join(
        c if c.isalnum() or c in "-_. " else "_" for c in app_name
    ).strip()
    host_dir = os.path.join(userdata_root(), safe)
    os.makedirs(host_dir, exist_ok=True)
    for sub in USERDATA_SUBDIRS:
        os.makedirs(os.path.join(host_dir, sub), exist_ok=True)
    # migrate existing data from the real prefix user dir (once)
    import shutil

    marker = os.path.join(host_dir, ".migrated")
    src = os.path.join(prefix_dir, "drive_c", "users", user)
    if os.path.isdir(src) and not os.path.exists(marker):
        for entry in os.listdir(src):
            s = os.path.join(src, entry)
            d = os.path.join(host_dir, entry)
            if os.path.exists(d):
                continue  # never overwrite
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            elif os.path.isfile(s):
                shutil.copy2(s, d)
        try:
            with open(marker, "w") as fh:
                fh.write("1")
        except OSError:
            pass
    return host_dir
