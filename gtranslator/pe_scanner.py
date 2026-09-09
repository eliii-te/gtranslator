"""gtranslator(i)™ — zero-dependency PE/executable scanner.

Reads just enough of the Windows PE format to answer the questions
winsecure needs: architecture, subsystem, embedded installer markers.
No external packages required (pure stdlib).

Reference:
  https://learn.microsoft.com/en-us/windows/win32/debug/pe-format
"""

from __future__ import annotations

import os
import struct

MACHINE_I386 = 0x014C
MACHINE_AMD64 = 0x8664
MACHINE_ARM64 = 0xAA64

MACHINE_NAMES = {
    MACHINE_I386: "x86",
    MACHINE_AMD64: "x86_64",
    MACHINE_ARM64: "arm64",
}

SUBSYSTEM_GUI = 2
SUBSYSTEM_CUI = 3

SUBSYSTEM_NAMES = {
    SUBSYSTEM_GUI: "windows-gui",
    SUBSYSTEM_CUI: "windows-console",
}

# Installer fingerprints. NSIS and Inno Setup append their payload +
# signature to the *end* of the file; InstallShield marks the header.
# (bytes, label)
INSTALLER_MARKERS = [
    (b"Nullsoft Installer", "nsis"),
    (b"NullsoftInst", "nsis"),
    (b"Inno Setup Setup Data", "inno"),
    (b"Inno Setup", "inno"),
    (b"InstallShield", "installshield"),
    (b"Squirrel.exe", "squirrel"),
    (b"WiX ", "wix"),
]

INSTALLER_NAME_HINTS = ("setup", "install", "update", "patch", "bootstrapper")


def _read(path: str) -> bytes:
    """Return raw file bytes (bounded for huge files)."""
    size = os.path.getsize(path)
    # We only need header + tail for markers; cap full read at 64 MB.
    if size > 64 * 1024 * 1024:
        head_n = 1024 * 1024
        tail_n = 1024 * 1024
        with open(path, "rb") as fh:
            head = fh.read(head_n)
            fh.seek(size - tail_n)
            tail = fh.read(tail_n)
        return head + tail
    with open(path, "rb") as fh:
        return fh.read()


def scan(path: str) -> dict:
    """Scan a Windows executable and return a structured report.

    Returns dict with keys:
      ok, error, mz, pe, machine, arch, subsystem, bits,
      sections, overlay_markers, is_installer, installer, size
    Never raises; errors are reported in the dict.
    """
    report = {
        "ok": False,
        "error": None,
        "mz": False,
        "pe": False,
        "machine": None,
        "arch": None,
        "bits": None,
        "subsystem": None,
        "subsystem_name": None,
        "sections": [],
        "installer": None,
        "is_installer": False,
        "size": 0,
    }

    try:
        report["size"] = os.path.getsize(path)
        data = _read(path)
    except OSError as exc:
        report["error"] = f"cannot read: {exc}"
        return report

    if len(data) < 0x40 or data[:2] != b"MZ":
        report["error"] = "not a Windows PE file (missing MZ header)"
        return report
    report["mz"] = True

    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 24 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        report["error"] = "MZ header present but no valid PE signature"
        return report
    report["pe"] = True

    coff = e_lfanew + 4
    machine, num_sections, _, _, _, opt_size, _ = struct.unpack_from(
        "<HHIIIHH", data, coff
    )
    report["machine"] = machine
    report["arch"] = MACHINE_NAMES.get(machine, f"unknown(0x{machine:04x})")
    report["bits"] = 64 if machine in (MACHINE_AMD64, MACHINE_ARM64) else 32

    # Optional header (PE32 vs PE32+) for subsystem.
    # The Subsystem field sits at offset 68 in *both* PE32 and PE32+
    # (PE32+ only differs earlier: 8-byte ImageBase instead of 4-byte
    # ImageBase+BaseOfData — net offset is identical).
    opt = coff + 20
    if opt + 70 <= len(data):
        magic = struct.unpack_from("<H", data, opt)[0]
        if magic in (0x10B, 0x20B):  # PE32 or PE32+
            subsystem = struct.unpack_from("<H", data, opt + 68)[0]
        else:
            subsystem = None
        report["subsystem"] = subsystem
        report["subsystem_name"] = SUBSYSTEM_NAMES.get(subsystem, str(subsystem))

    # Section table.
    sec_off = opt + opt_size
    if sec_off + num_sections * 40 <= len(data):
        for i in range(num_sections):
            base = sec_off + i * 40
            name = data[base : base + 8].rstrip(b"\0").decode("latin-1", "replace")
            vsize, vaddr, raw_size, raw_ptr = struct.unpack_from(
                "<IIII", data, base + 8
            )
            report["sections"].append(
                {
                    "name": name,
                    "virtual_size": vsize,
                    "raw_size": raw_size,
                }
            )

    # Installer fingerprint scan: header + tail are already concatenated.
    tail = data[-512 * 1024 :] if len(data) > 512 * 1024 else data
    for marker, label in INSTALLER_MARKERS:
        if marker in tail or marker in data[:512 * 1024]:
            report["installer"] = label
            report["is_installer"] = True
            break

    return report


def classify(path: str) -> dict:
    """High-level classification used by the launcher.

    kind: "installer" | "application" | "invalid"
    installer: detected family or None
    """
    rep = scan(path)
    if not rep["pe"]:
        rep["kind"] = "invalid"
        return rep

    # Squirrel "Update.exe" is a bootstrapper, NSIS/Inno/InstallShield
    # are installers; anything else is treated as a (portable) app.
    if rep["installer"] or rep["is_installer"]:
        rep["kind"] = "installer"
    else:
        name = os.path.basename(path).lower()
        if any(h in name for h in INSTALLER_NAME_HINTS) and name.endswith(
            (".exe", ".msi")
        ):
            rep["installer"] = "unknown"
            rep["is_installer"] = True
            rep["kind"] = "installer"
        elif name.endswith(".msi"):
            rep["installer"] = "msi"
            rep["is_installer"] = True
            rep["kind"] = "installer"
        else:
            rep["kind"] = "application"
    return rep
