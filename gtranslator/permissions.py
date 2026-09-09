"""gtranslator permission prompts.

The rights pyramid, bottom-up:
  1. host filesystem      — denied by the sandbox itself (winsecure™)
  2. root / admin         — denied, always
  3. background activity  — denied unless the user opts in
  4. network              — ask on first use, then remember
  5. install actions      — always ask: "App X wants to install Y. Allow?"

This module renders those asks as a desktop dialog (tkinter) and falls
back to a plain console question when no display/UI is available.
"""

from __future__ import annotations

import subprocess
import sys


def ask(title: str, question: str, default: bool = False) -> bool:
    """Ask the user a yes/no question. Returns True when allowed."""
    # try a GUI prompt first (zenity, then tkinter)
    if _ask_zenity(title, question):
        return True
    gui = _ask_tk(title, question)
    if gui is not None:
        return gui
    # console fallback
    hint = " [y/N] " if not default else " [Y/n] "
    try:
        answer = input(f"{question}{hint}").strip().lower()
    except EOFError:
        return default
    if not answer:
        return default
    return answer in ("y", "yes", "j", "ja")


def _ask_zenity(title: str, question: str) -> bool | None:
    try:
        import shutil

        zenity = shutil.which("zenity")
        if not zenity:
            return None
        proc = subprocess.run(
            [zenity, "--question", "--title", title, "--text", question,
             "--width=420"],
            capture_output=True,
        )
        return proc.returncode == 0
    except Exception:
        return None


def _ask_tk(title: str, question: str) -> bool | None:
    try:
        import tkinter as tk
    except ImportError:
        return None
    result = {"value": None}
    try:
        root = tk.Tk()
        root.title(title)
        root.attributes("-topmost", True)
        root.configure(bg="#0f1115")
        root.geometry("460x190")
        tk.Label(
            root, text=title, bg="#0f1115", fg="#6ee7b7",
            font=("Sans", 14, "bold"), wraplength=420,
        ).pack(pady=(18, 6), padx=20)
        tk.Label(
            root, text=question, bg="#0f1115", fg="#e5e7eb",
            font=("Sans", 11), wraplength=420, justify="left",
        ).pack(pady=(0, 14), padx=20)

        def yes():
            result["value"] = True
            root.destroy()

        def no():
            result["value"] = False
            root.destroy()

        btn_frame = tk.Frame(root, bg="#0f1115")
        btn_frame.pack()
        tk.Button(btn_frame, text="Allow", command=yes,
                  bg="#059669", fg="white", width=10, relief="flat",
                  activebackground="#047857").pack(side="left", padx=8)
        tk.Button(btn_frame, text="Deny", command=no,
                  bg="#374151", fg="white", width=10, relief="flat",
                  activebackground="#1f2937").pack(side="left", padx=8)
        root.mainloop()
        return result["value"]
    except Exception:
        return None
