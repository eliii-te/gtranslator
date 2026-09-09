"""gtranslator™ CLI — the GlassyOS Windows-translator.

Click a Windows .exe  → gtranslator(i)™ analyses it → winsecure™ opens
an isolated bubble → splash: "starting with gtranslator™" → app runs.
On the first successful run the .exe becomes a .gwp (Glassy-Windows-
Program) that carries its whole setup, so the next start is instant.

Commands:
  gtranslator run <file.exe|file.gwp>   launch (double-click handler)
  gtranslator install <setup.exe>       run installer, register result
  gtranslator info <file>               gtranslator(i)™ analysis
  gtranslator prefixes list|remove      manage app state
  gtranslator mime --register           .exe/.gwp → gtranslator (one-time)
  gtranslator doctor                    environment check
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import urllib.parse

from . import __version__
from . import gwp as gwp_mod
from . import pe_scanner, permissions, prefix, sandbox
from .display import XephyrServer

EXE_BUBBLE_PATH = "/app/application.exe"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _resolve(path: str) -> str:
    """Strip file:// URIs a desktop handler may pass via %u."""
    if path.startswith("file://"):
        return urllib.parse.unquote(urllib.parse.urlparse(path).path)
    return os.path.abspath(path)


def _parse_args(raw: str | None) -> list[str]:
    """Split an --args string into argv items."""
    if not raw:
        return []
    try:
        import shlex

        return shlex.split(raw)
    except ValueError:
        return raw.split()


def _require_tool(name: str, pacman: str) -> str | None:
    found = shutil.which(name)
    if not found:
        print(f"  ✗ {name}: MISSING  →  install: sudo pacman -S {pacman}")
    else:
        print(f"  ✓ {name}: {found}")
    return found


def _launcher_script() -> str:
    found = shutil.which("gtranslator")
    if found:
        return found
    return os.path.expanduser("~/.local/bin/gtranslator")


# --------------------------------------------------------------------------
# bubble launch core
# --------------------------------------------------------------------------

def _launch_bubble(
    *,
    app_name: str,
    arch: str,
    aid: str,
    network: bool,
    exe_host: str | None,
    start_target: str | None,
    app_args: list[str] | None = None,
) -> int:
    """Launch a Windows app in an isolated Xephyr display.

    The Xephyr window behaves like any normal host window (Hyprland
    tiles/manages it); inside, openbox runs every Windows app
    fullscreen on the isolated display. Wine runs in a worker thread
    while the splash shows; the launcher stays alive until the app
    exits (never kills a running app).
    """
    import threading

    from . import splash as splash_mod
    from .display import hyprland_focus, hyprland_prepare

    # runtime window rules (center) BEFORE the Xephyr window maps
    hyprland_prepare()

    xephyr = XephyrServer(
        title=f"gtranslator™ — {app_name}", geometry="1280x800x24"
    )
    try:
        xephyr.start()
    except RuntimeError as exc:
        print(f"gtranslator™: display error: {exc}")
        return 3
    app_display = xephyr.display

    # right after the display is up: focus so the window joins the
    # desktop like a normal app (centering is handled by the runtime
    # windowrule set in hyprland_prepare above)
    hyprland_focus()

    # openbox inside: apps get window management and run fullscreen on
    # the isolated display (see gtranslator openbox rc.xml)
    wm_proc = None
    wm = shutil.which("openbox")
    rc = os.path.join(sandbox.DATA_HOME, "openbox", "rc.xml")
    if wm:
        wm_env = dict(os.environ, DISPLAY=app_display)
        cmd = [wm]
        if os.path.exists(rc):
            cmd += ["--config-file", rc]
        wm_proc = subprocess.Popen(
            cmd, env=wm_env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(1.0)  # let openbox map its frame

    paths = prefix.ensure_dirs(aid)
    bubble = sandbox.Bubble(
        display=app_display,
        prefix=paths["prefix"],
        app_home=paths["home"],
        exe_host_path=exe_host,
        exe_bubble_path=EXE_BUBBLE_PATH if exe_host else None,
        arch=arch,
        network=network,
    )

    from .display import hyprland_focus

    stop = threading.Event()
    result: dict = {"rc": None}

    def worker() -> None:
        try:
            prefix.ensure_wineboot(bubble)
            # visible user-data folder (~/gtranslator/<App>) with the
            # Windows profile layout; C:\users\<user> maps onto it
            ud = prefix.prepare_userdata(app_name, bubble.prefix)
            if ud:
                bubble.userdata_host = ud
                bubble.userdata_user = prefix.wine_user_name(bubble.prefix)
            if start_target:
                wine_target = os.path.join(
                    "/wineprefix", "drive_c", start_target.lstrip("/")
                )
                cmd = bubble.build(["wine", wine_target] + (app_args or []))
            else:
                cmd = bubble.build(
                    ["wine", EXE_BUBBLE_PATH] + (app_args or [])
                )
            print(f"gtranslator™: bubble ready on {app_display}, "
                  "starting application …")
            proc = subprocess.run(cmd)
            result["rc"] = proc.returncode
        except Exception as exc:  # surfaced after splash closes
            print(f"gtranslator™: launch error: {exc}")
            result["rc"] = 1
        finally:
            stop.set()

    wthread = threading.Thread(target=worker, daemon=True)
    wthread.start()

    # poll the app display so the splash closes on the first window
    poller = threading.Thread(
        target=splash_mod.wait_for_window_or_stop,
        args=(app_display, stop),
        daemon=True,
    )
    poller.start()

    splash_mod.show_splash_blocking(app_name, stop)
    hyprland_focus()  # app window is up — pull it into focus
    # wait for the app to close itself — NEVER kill a running app
    wthread.join()

    # app is done → tear down the isolated display
    try:
        if wm_proc and wm_proc.poll() is None:
            wm_proc.terminate()
            wm_proc.wait(timeout=3)
    except Exception:
        pass
    xephyr.stop()
    return result["rc"] if result["rc"] is not None else 1


def _register_launcher_entry(name: str, target: str) -> str:
    """Create a .desktop entry so the app shows up in the app launcher."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:40]
    desktop = os.path.join(apps_dir, f"gtranslator-{safe}.desktop")
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name} (gtranslator™)\n"
        "Comment=Windows app in a winsecure™ bubble — GWP\n"
        f"Exec={_launcher_script()} run {target}\n"
        "Icon=applications-wine\n"
        "Terminal=false\n"
        "Categories=Application;Utility;\n"
        "X-GlassyOS-WindowsApp=true\n"
        "X-GlassyOS-Privileges=minimal\n"
    )
    with open(desktop, "w") as fh:
        fh.write(content)
    os.chmod(desktop, 0o755)
    return desktop


# --------------------------------------------------------------------------
# run: .exe (first run → converts to .gwp)
# --------------------------------------------------------------------------

def run_exe(path: str, args: argparse.Namespace) -> int:
    rep = pe_scanner.classify(path)
    if not rep.get("pe"):
        print(f"gtranslator™: '{path}' is not a valid Windows executable")
        return 2

    name = os.path.basename(path)
    arch = "x86_64" if rep.get("bits") == 64 else "x86"
    kind = "installer" if rep.get("is_installer") or args.force_installer else "application"

    if kind == "installer":
        family = rep.get("installer") or "unknown"
        print(f"gtranslator™: {name} is an installer ({family}) — "
              "it will run isolated; after it finishes, gtranslator(i)™ "
              "locates the installed program.")
    print(f"gtranslator™: launching {name} with winsecure™ isolation "
          f"[{rep.get('arch')}]")

    aid = prefix.app_id(path)
    paths = prefix.ensure_dirs(aid)

    # permission prompts before launch
    if kind == "installer":
        ok = permissions.ask(
            "gtranslator™ — installation",
            f"'{name}' is an installer and wants to install software "
            "into its isolated bubble.\n"
            "No host files, no root, no background — ever.\nAllow?",
            default=True,
        )
        if not ok:
            print("gtranslator™: installation denied by user")
            return 0
    network = args.network
    if network:
        ok = permissions.ask(
            "gtranslator™ — network request",
            f"'{name}' requests network access inside the bubble.\n"
            "Allow (isolated, still no host access)?",
            default=False,
        )
        if not ok:
            print("gtranslator™: network denied — continuing offline")
            network = False

    rc = _launch_bubble(
        app_name=name,
        arch=arch,
        aid=aid,
        network=network,
        exe_host=path,
        start_target=None,
        app_args=_parse_args(getattr(args, "args", None)),
    )

    # first successful run → become a .gwp
    if rc == 0 and not args.no_gwp:
        _convert_to_gwp(path, rep, aid, kind, arch, network, paths)
    elif rc != 0:
        print(f"gtranslator™: application exited with code {rc} — "
              "not converting to .gwp")
    return rc


def _convert_to_gwp(exe_path, rep, aid, kind, arch, network, paths) -> None:
    """Turn the .exe into a .gwp next to it (rename semantics).

    After the first successful run we always check whether the run
    installed a real program into the prefix (many installers are not
    detected as such — e.g. 7-Zip). If found, the .gwp points at the
    installed app instead of re-running the installer.
    """
    base_name = os.path.splitext(os.path.basename(exe_path))[0]
    manifest = gwp_mod.default_manifest()
    manifest["app"].update({
        "name": base_name,
        "id": aid,
        "kind": kind,
        "installer": rep.get("installer"),
        "arch": arch,
        "original_exe": os.path.basename(exe_path),
    })
    manifest["setup"].update({
        "prefix_id": aid,
        "network": network,
    })
    manifest["permissions"].update({
        "network": network,
        "install": "allow",
    })
    manifest["stats"]["first_run"] = time.time()

    # always look for a program the run may have installed
    start_target = None
    payload = None
    found = prefix.discover_installed_exe(paths["prefix"])
    if found:
        drive_c = os.path.join(paths["prefix"], "drive_c")
        rel = os.path.relpath(found[0], drive_c)
        manifest["app"]["kind"] = "installed"
        manifest["setup"]["start_target"] = rel
        print(f"gtranslator(i)™: found installed program: {rel}")
        print("  → the .gwp will start this app, not the installer")
        payload = {}  # installer exe is replaced by the .gwp manifest
    else:
        payload = {os.path.basename(exe_path): exe_path}

    gwp_path = gwp_mod.convert_exe_to_gwp(
        exe_path, manifest,
        payload_files=payload,
        keep_exe=args_keep_exe(),
    )
    _register_launcher_entry(base_name, gwp_path)
    print(f"gtranslator™: {os.path.basename(exe_path)} → "
          f"{os.path.basename(gwp_path)}  (Glassy-Windows-Program)")
    print(f"gtranslator™: added to app launcher — double-click the .gwp "
          "from now on for an instant start.")


_keep_exe_flag = False


def args_keep_exe() -> bool:
    return _keep_exe_flag


# --------------------------------------------------------------------------
# run: .gwp (instant start with stored setup)
# --------------------------------------------------------------------------

def run_gwp(path: str, args: argparse.Namespace) -> int:
    manifest = gwp_mod.read(path)
    app = manifest.get("app", {})
    setup = manifest.get("setup", {})
    perms = manifest.get("permissions", gwp_mod.DEFAULT_PERMISSIONS)
    name = app.get("name") or os.path.basename(path)
    aid = setup.get("prefix_id") or app.get("id") or prefix.app_id(path)
    arch = app.get("arch", "x86_64")
    kind = app.get("kind", "application")

    print(f"gtranslator™: {name} (.gwp) — starting with stored setup …")
    paths = prefix.ensure_dirs(aid)

    network = bool(args.network or setup.get("network"))
    # ask once if this gwp wants network but never got permission
    if setup.get("network") and not perms.get("network"):
        ok = permissions.ask(
            "gtranslator™ — network request",
            f"'{name}' is configured to use the network.\n"
            "Allow network inside the isolated bubble?",
            default=False,
        )
        network = ok

    start_target = setup.get("start_target")
    exe_host = None
    if not start_target:
        exe_host = gwp_mod.extract_payload(path, paths["exe_cache"])

    rc = _launch_bubble(
        app_name=name,
        arch=arch,
        aid=aid,
        network=network,
        exe_host=exe_host,
        start_target=start_target,
    )
    if rc == 0:
        manifest.setdefault("stats", {})
        manifest["stats"]["run_count"] = manifest["stats"].get("run_count", 0) + 1
        manifest["stats"]["last_run"] = time.time()
        if getattr(args, "windowed", False):
            manifest.setdefault("setup", {})["windowed"] = True
        try:
            gwp_mod.create(path, manifest)
        except Exception:
            pass
    return rc


# --------------------------------------------------------------------------
# commands
# --------------------------------------------------------------------------

def cmd_run(args: argparse.Namespace) -> int:
    global _keep_exe_flag
    _keep_exe_flag = bool(getattr(args, "keep_exe", False))
    path = _resolve(args.file)
    if not os.path.isfile(path):
        print(f"gtranslator™: file not found: {path}")
        return 1
    if gwp_mod.is_gwp(path):
        return run_gwp(path, args)
    return run_exe(path, args)


def cmd_info(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    print(f"gtranslator(i)™ analysis: {path}")
    if gwp_mod.is_gwp(path):
        manifest = gwp_mod.read(path)
        print(f"  format         : gwp v{manifest.get('version')}")
        app = manifest.get("app", {})
        setup = manifest.get("setup", {})
        perms = manifest.get("permissions", {})
        for key, val in app.items():
            if val:
                print(f"  app.{key:<10}: {val}")
        for key, val in setup.items():
            if val:
                print(f"  setup.{key:<8}: {val}")
        print("  permissions    : "
              + ", ".join(f"{k}={v}" for k, v in perms.items()))
        return 0
    rep = pe_scanner.classify(path)
    for key in ("size", "mz", "pe", "arch", "bits", "subsystem_name",
                "installer", "is_installer", "kind", "error"):
        val = rep.get(key)
        if val is None or val is False or val == "":
            continue
        print(f"  {key:<14}: {val}")
    if rep.get("kind") == "installer":
        print("  → INSTALLER — will run isolated; installed program is "
              "located afterwards")
    elif rep.get("kind") == "application":
        print("  → portable APPLICATION — first run converts it to a .gwp")
    else:
        print("  → not a valid Windows executable")
    return 0 if rep.get("pe") else 2


def cmd_doctor(args: argparse.Namespace) -> int:
    print("gtranslator™ doctor — environment check")
    print(f"  gtranslator version : {__version__}")
    _require_tool("bwrap", "bubblewrap")
    _require_tool("wine", "wine-staging") or _require_tool("wine", "wine")
    _require_tool("Xephyr", "xorg-server-xephyr")
    try:
        import tkinter  # noqa: F401
        print("  ✓ tkinter: available (splash + permission dialogs)")
    except ImportError:
        print("  ⚠ tkinter: MISSING — splash falls back to console "
              "(install: python tk)")
    ok = all(shutil.which(t) for t in ("bwrap", "wine", "Xephyr"))
    print()
    if ok:
        print("  ✓ everything ready — happy translating!")
    else:
        print("  install missing tools, then re-run: gtranslator doctor")
    return 0 if ok else 1


def cmd_prefixes(args: argparse.Namespace) -> int:
    if args.action == "list":
        entries = prefix.list_prefixes()
        if not entries:
            print("no app prefixes yet — run something first!")
            return 0
        for e in entries:
            print(f"  {e['id']:<50} {prefix.human_size(e['size'])}")
        return 0
    if args.action == "remove":
        ok = prefix.remove_prefix(args.id)
        print(f"removed {args.id}" if ok else f"no prefix named {args.id}")
        return 0 if ok else 1
    print("unknown prefixes action")
    return 1


def cmd_mime(args: argparse.Namespace) -> int:
    """Register .exe/.gwp so double-click opens gtranslator."""
    if args.action == "register":
        return mime_register()
    if args.action == "status":
        mime_status()
        return 0
    print("unknown mime action")
    return 1


def _write_mime_package() -> str:
    """User-level mimetype definitions for .gwp (+ tighten .exe)."""
    mime_dir = os.path.expanduser("~/.local/share/mime/packages")
    os.makedirs(mime_dir, exist_ok=True)
    xml = os.path.join(mime_dir, "gtranslator.xml")
    content = """<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/vnd.glassywindows.gwp">
    <comment>Glassy-Windows-Program</comment>
    <glob pattern="*.gwp"/>
    <icon name="applications-wine"/>
  </mime-type>
  <mime-type type="application/x-ms-dos-executable">
    <comment>Windows executable (gtranslator™)</comment>
    <glob pattern="*.exe"/>
    <icon name="applications-wine"/>
  </mime-type>
</mime-info>
"""
    with open(xml, "w") as fh:
        fh.write(content)
    return xml


def _write_handler_desktop() -> str:
    apps_dir = os.path.expanduser("~/.local/share/applications")
    os.makedirs(apps_dir, exist_ok=True)
    desktop = os.path.join(apps_dir, "gtranslator-handler.desktop")
    content = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=gtranslator™ (Windows apps)\n"
        "Comment=Run Windows programs isolated with winsecure™\n"
        f"Exec={_launcher_script()} run %u\n"
        "Icon=applications-wine\n"
        "Terminal=false\n"
        "MimeType=application/x-ms-dos-executable;"
        "application/x-msdownload;application/vnd.glassywindows.gwp;\n"
        "NoDisplay=true\n"
    )
    with open(desktop, "w") as fh:
        fh.write(content)
    os.chmod(desktop, 0o755)
    return desktop


def mime_register() -> int:
    _write_mime_package()
    _write_handler_desktop()

    mime_dir = os.path.expanduser("~/.local/share/mime")
    apps_dir = os.path.expanduser("~/.local/share/applications")
    subprocess.run(["update-mime-database", mime_dir], check=False)
    subprocess.run(["update-desktop-database", apps_dir], check=False)

    # make gtranslator the default handler for .exe and .gwp
    mimeapps = os.path.expanduser("~/.config/mimeapps.list")
    os.makedirs(os.path.dirname(mimeapps), exist_ok=True)
    defaults: dict[str, list[str]] = {}
    if os.path.exists(mimeapps):
        section = None
        for line in open(mimeapps):
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                defaults.setdefault(section, [])
            elif "=" in line and section == "Default Applications":
                key, val = line.split("=", 1)
                defaults["Default Applications"].append((key, val))
    # rewrite simply & idempotently
    with open(mimeapps, "w") as fh:
        fh.write("[Default Applications]\n")
        entries = {
            "application/x-ms-dos-executable": "gtranslator-handler.desktop",
            "application/x-msdownload": "gtranslator-handler.desktop",
            "application/vnd.glassywindows.gwp": "gtranslator-handler.desktop",
        }
        # preserve any pre-existing defaults that are not ours
        for key, val in defaults.get("Default Applications", []):
            if key not in entries:
                entries[key] = val
        for mime, handler in entries.items():
            fh.write(f"{mime}={handler}\n")
    print("gtranslator™: registered — double-clicking .exe / .gwp now "
          "starts gtranslator")
    return 0


def mime_status() -> None:
    for f in (
        os.path.expanduser("~/.local/share/mime/packages/gtranslator.xml"),
        os.path.expanduser("~/.local/share/applications/gtranslator-handler.desktop"),
    ):
        print(f"  {'✓' if os.path.exists(f) else '✗'} {f}")


def cmd_desktop(args: argparse.Namespace) -> int:
    path = _resolve(args.file)
    if gwp_mod.is_gwp(path):
        manifest = gwp_mod.read(path)
        name = manifest.get("app", {}).get("name") or os.path.basename(path)
    else:
        name = os.path.splitext(os.path.basename(path))[0]
    out = _register_launcher_entry(name, path)
    print(f"created: {out}")
    return 0


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gtranslator",
        description="gtranslator™ — Windows apps on GlassyOS, translated. "
                    "Click a .exe, get an isolated winsecure™ bubble, "
                    "instant .gwp starts afterwards.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run a Windows .exe or .gwp")
    r.add_argument("file")
    r.add_argument("--network", action="store_true",
                   help="request network access inside the bubble")
    r.add_argument("--keep-exe", action="store_true",
                   help="keep the original .exe after converting to .gwp")
    r.add_argument("--no-gwp", action="store_true",
                   help="do not convert to .gwp after the first run")
    r.add_argument("--args", metavar="ARGS",
                   help='extra arguments for the app, e.g. --args "/S" '
                        '(silent installers)')
    r.add_argument("--force-installer", action="store_true")
    r.set_defaults(func=cmd_run)

    i = sub.add_parser("install", help="run a Windows installer")
    i.add_argument("file")
    i.add_argument("--network", action="store_true")
    i.add_argument("--keep-exe", action="store_true")
    i.add_argument("--no-gwp", action="store_true")
    i.add_argument("--args", metavar="ARGS",
                   help='extra arguments for the installer, e.g. --args "/S"')
    i.set_defaults(func=cmd_run, force_installer=True)

    info = sub.add_parser("info", help="gtranslator(i)™ analysis")
    info.add_argument("file")
    info.set_defaults(func=cmd_info)

    d = sub.add_parser("doctor", help="environment check")
    d.set_defaults(func=cmd_doctor)

    pf = sub.add_parser("prefixes", help="manage isolated app state")
    pf.add_argument("action", choices=["list", "remove"])
    pf.add_argument("id", nargs="?")
    pf.set_defaults(func=cmd_prefixes)

    mime = sub.add_parser("mime", help="register double-click handling")
    mime.add_argument("action", choices=["register", "status"])
    mime.set_defaults(func=cmd_mime)

    de = sub.add_parser("desktop", help="create an app-launcher entry")
    de.add_argument("file")
    de.set_defaults(func=cmd_desktop)

    return p


def main(argv: list[str] | None = None) -> int:
    import logging
    import traceback

    log_dir = sandbox.DATA_HOME
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        filename=os.path.join(log_dir, "gtranslator.log"),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ngtranslator™: interrupted")
        return 130
    except Exception as exc:  # never die silently on double-click
        tb = traceback.format_exc()
        logging.error("%s", tb)
        print(f"gtranslator™: error: {exc}", file=sys.stderr)
        print(tb, file=sys.stderr)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "gtranslator™ error",
                f"{exc}\n\nDetails: {os.path.join(log_dir, 'gtranslator.log')}",
            )
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
