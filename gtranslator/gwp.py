"""gtranslator .gwp format — Glassy-Windows-Program.

A .gwp is a single-file container (ZIP) that represents one Windows
program on GlassyOS:

    foo.gwp
    ├── gwp.json          # metadata: wine/gtranslator setup, permissions
    └── payload/
        └── foo.exe       # the original executable (portable apps)

After a Windows .exe has been launched successfully for the first time,
gtranslator converts it into a .gwp: the app now carries everything
needed to start fast (no re-scan, no re-setup) and GlassyOS can treat
it as a first-class citizen — GWP = top of the rights pyramid, root is
always denied, background activity is always blocked unless the user
explicitly allows it.

Installed apps (from installers) are stored *in the isolated prefix*
instead; their .gwp holds a start_target path inside the prefix.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import zipfile

GWP_MIME = "application/vnd.glassywindows.gwp"
GWP_EXT = ".gwp"

MANIFEST = "gwp.json"
PAYLOAD_DIR = "payload/"

DEFAULT_PERMISSIONS = {
    "root": False,            # NEVER — hard rule of the rights pyramid
    "background": False,      # NEVER without explicit user consent
    "network": False,         # opt-in per launch
    "install": "ask",         # "ask" | "allow" | "deny"
    "host_files": False,      # no host filesystem access, ever (sandbox)
}


def default_manifest() -> dict:
    m = {
        "format": "gwp",
        "version": 1,
        "app": {
            "name": "",
            "id": "",
            "kind": "application",   # "application" | "installer" | "installed"
            "installer": None,       # detected family (nsis/inno/...)
            "arch": "x86_64",        # wine arch
            "original_exe": "",
        },
        "setup": {
            "prefix_id": "",
            "start_target": None,    # exe inside prefix (installed apps)
            "network": False,
            "wine_args": [],
            "geometry": "1280x800x24",
        },
        "permissions": dict(DEFAULT_PERMISSIONS),
        "stats": {"first_run": None, "last_run": None, "run_count": 0},
    }
    return m


# --------------------------------------------------------------------------
# read / create / convert
# --------------------------------------------------------------------------

def read(path: str) -> dict:
    """Read a .gwp and return its manifest dict."""
    with zipfile.ZipFile(path) as zf:
        with zf.open(MANIFEST) as fh:
            return json.loads(fh.read().decode("utf-8"))


def _write_manifest(zf: zipfile.ZipFile, manifest: dict) -> None:
    data = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")
    zf.writestr(MANIFEST, data)


def create(
    gwp_path: str,
    manifest: dict,
    payload_files: dict[str, str] | None = None,
) -> None:
    """Create a .gwp. payload_files maps archive path -> host file.

    Atomic: writes to a temp file first and renames — a failure (e.g.
    payload file vanished mid-write) can never leave a half-written
    .gwp behind.
    """
    payload_files = payload_files or {}
    tmp_path = gwp_path + ".tmp"
    try:
        with zipfile.ZipFile(
            tmp_path, "w", compression=zipfile.ZIP_DEFLATED
        ) as zf:
            _write_manifest(zf, manifest)
            for arc, host in payload_files.items():
                zf.write(host, arcname=os.path.join(PAYLOAD_DIR, arc))
        os.replace(tmp_path, gwp_path)
    except Exception:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise


def convert_exe_to_gwp(
    exe_path: str,
    manifest: dict,
    keep_exe: bool = False,
    payload_files: dict[str, str] | None = None,
) -> str:
    """Turn a .exe into a .gwp sitting next to it (rename semantics).

    The original file is replaced by the container unless keep_exe.
    payload_files=None → the .exe itself becomes the payload.
    payload_files={}   → manifest-only .gwp (installed apps).
    Returns the new .gwp path.
    """
    if payload_files is None:
        payload_files = {os.path.basename(exe_path): exe_path}
    gwp_path = os.path.splitext(exe_path)[0] + GWP_EXT
    create(gwp_path, manifest, payload_files)
    if not keep_exe:
        os.remove(exe_path)
    return gwp_path


# --------------------------------------------------------------------------
# run support
# --------------------------------------------------------------------------

def extract_payload(gwp_path: str, dest_dir: str) -> str:
    """Extract the payload exe to dest_dir, return its host path."""
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(gwp_path) as zf:
        names = [
            n for n in zf.namelist()
            if n.startswith(PAYLOAD_DIR) and not n.endswith("/")
        ]
        if not names:
            raise RuntimeError(f"{gwp_path}: gwp has no payload executable")
        name = names[0]
        target = os.path.join(dest_dir, os.path.basename(name))
        # only extract if missing or manifest changed — speed matters here
        with zf.open(name) as src, open(target, "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.chmod(target, 0o755)
        return target


def is_gwp(path: str) -> bool:
    return path.lower().endswith(GWP_EXT)
