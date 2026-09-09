"""winsecure™ — bubblewrap sandbox profiles for gtranslator.

Every Windows program runs inside its own bubble:
  - no host filesystem access (only the gtranslator data dir is mounted)
  - no network by default (opt-in via --network)
  - no admin rights, no host processes, private /tmp, private PID ns
  - dies with its parent, so nothing survives the app closing

This is the same isolation primitive Flatpak uses (bubblewrap).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field

# Root of all gtranslator state (prefixes, home dirs, downloads).
DATA_HOME = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "gtranslator",
)

# Inside the bubble, the app sees this as $HOME.
BUBBLE_HOME = "/home/app"

# Host dirs the bubble gets read-only. Wine needs system libs/binfmt.
# NOTE: no /lib or /lib64 here — on usrmerge systems (Arch/GlassyOS)
# those are symlinks into /usr and get re-created via --symlink below.
RO_BIND_HOST = [
    "/usr",
    "/etc",
    "/opt",
    "/nix/store",  # harmless if absent
]

# /bin, /lib, /lib64 are symlinks to /usr on modern distros; bwrap
# builds an empty root so those links must be re-created explicitly.
USRMERGE_SYMLINKS = [
    ("usr/bin", "/bin"),
    ("usr/lib", "/lib"),
    ("usr/lib64", "/lib64"),
    ("usr/sbin", "/sbin"),
]

# /sys pieces some wine builds poke at (read-only, best effort).
SYS_RO_BINDS = [
    "/sys/dev/block",
    "/sys/dev/char",
]


def wine_arch_for(app_arch: str) -> str:
    """Map an app's bitness to a WINEARCH value.

    Modern Wine (>= 9, wow64-only builds like wine-staging 11.x) refuses
    to create win32 prefixes ("WINEARCH is set to 'win32' but this is not
    supported in wow64 mode") — but wow64 wine runs 32-bit apps fine in
    a win64 prefix. Older 32-bit-only wine needs win32 for x86 apps.
    """
    has_wine64 = shutil.which("wine64") or os.path.exists(
        "/usr/lib/wine/wine64"
    )
    if has_wine64:
        return "win64"   # wow64 handles x86 apps in a win64 prefix
    return "win64" if app_arch == "x86_64" else "win32"


@dataclass
class Bubble:
    """A fully isolated execution context for one Windows app."""

    display: str                  # e.g. ":90" — isolated Xephyr display
    prefix: str                   # WINEPREFIX (inside data dir, write-mounted)
    app_home: str                 # per-app $HOME inside data dir
    exe_host_path: str | None = None   # optional .exe on the *host*
    exe_bubble_path: str | None = None # where the app sees its .exe
    arch: str = "x86_64"          # wine arch: x86_64 or x86 (win64/win32)
    network: bool = False
    env: dict = field(default_factory=dict)
    writable_dirs: list = field(default_factory=list)  # extra host->bubble binds
    userdata_host: str | None = None  # host dir shown as C:\users\<user>
    userdata_user: str | None = None  # windows user name ("elias")

    def _mounts(self) -> list[str]:
        args = []
        for host_dir in RO_BIND_HOST:
            if os.path.isdir(host_dir):
                args += ["--ro-bind", host_dir, host_dir]
        if os.path.isdir("/usr") and os.path.islink("/bin"):
            for target, link in USRMERGE_SYMLINKS:
                args += ["--symlink", target, link]
        else:
            # non-usrmerge: bind the real dirs directly
            for d in ("/bin", "/lib", "/lib64", "/sbin"):
                if os.path.isdir(d):
                    args += ["--ro-bind", d, d]
        # /sys is not fully bindable; bind a few safe nodes ro.
        for node in SYS_RO_BINDS:
            if os.path.exists(node):
                args += ["--ro-bind", node, node]
        # Data dir: host prefix/home are writable inside the bubble.
        args += ["--bind", self.prefix, "/wineprefix"]
        args += ["--bind", self.app_home, BUBBLE_HOME]
        # Visible user-data: C:\users\<user> of the app maps to a real,
        # browsable folder (~/gtranslator/<App> with AppData, Documents…)
        if self.userdata_host and self.userdata_user:
            target = os.path.join(
                "/wineprefix/drive_c/users", self.userdata_user
            )
            args += ["--dir", target, "--bind", self.userdata_host, target]
        # The executable itself is ro-bound at a fixed path (optional:
        # apps installed inside the prefix need no extra mount).
        if self.exe_host_path and self.exe_bubble_path:
            args += ["--ro-bind", self.exe_host_path, self.exe_bubble_path]
        # The isolated X display lives on the *host* /tmp; its unix
        # socket must be mounted into the bubble or Wine can't connect
        # ("no driver could be loaded"). Same trick Flatpak uses.
        if self.display and self.display.startswith(":"):
            num = self.display.lstrip(":").split(".")[0]
            sock = f"/tmp/.X11-unix/X{num}"
            if os.path.exists(sock):
                args += ["--dir", "/tmp/.X11-unix",
                         "--ro-bind", sock, sock]
        for host_dir, bubble_dir in self.writable_dirs:
            os.makedirs(host_dir, exist_ok=True)
            args += ["--bind", host_dir, bubble_dir]
        return args

    def build(self, command: list[str]) -> list[str]:
        """Return the full bwrap argv for this bubble."""
        env_extra = {
            "HOME": BUBBLE_HOME,
            "DISPLAY": self.display,
            "WINEPREFIX": "/wineprefix",
            "WINEDEBUG": "-all",
            # NOTE: no WINEARCH here on purpose — modern wow64-only
            # wine (11.x staging) rejects win32 prefixes, and wine's own
            # default (win64) runs both 64- and 32-bit apps via wow64.
            "PATH": "/usr/bin:/usr/local/bin:/wineprefix/drive_c/windows",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "LC_ALL": os.environ.get("LC_ALL", ""),
            "XDG_RUNTIME_DIR": "/tmp/xdg",
            "PULSE_SERVER": "",  # no audio in MVP bubble
        }
        env_extra.update(self.env)

        argv = [
            "bwrap",
            "--unshare-all",          # net + ipc + pid + uts + cgroup + user
            "--die-with-parent",
            "--new-session",
            "--clearenv",
        ]
        if self.network:
            # undo the net part of --unshare-all, keep the rest
            argv = [a for a in argv if a != "--unshare-all"]
            argv += [
                "--unshare-ipc",
                "--unshare-pid",
                "--unshare-uts",
                "--unshare-cgroup",
                "--share-net",
            ]
        for key, val in env_extra.items():
            if val:
                argv += ["--setenv", key, val]
        argv += [
            "--proc", "/proc",
            "--dev", "/dev",
            # /tmp as plain dir in the ephemeral rootfs (NOT --tmpfs):
            # a root-owned tmpfs makes Wine refuse with
            # "'/tmp' is not owned by you". The rootfs itself is already
            # an ephemeral tmpfs, so /tmp stays private per launch.
            "--dir", "/tmp",
            "--dir", "/tmp/xdg",
            "--dir", "/home",
            "--dir", "/home/app",
            "--dir", "/wineprefix",
        ]
        argv += self._mounts()
        argv += ["--"] + command
        return argv


def require_bwrap() -> str | None:
    """Return path to bwrap or None if unavailable."""
    return shutil.which("bwrap")
