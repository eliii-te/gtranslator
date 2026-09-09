"""gtranslator™ — Windows apps on GlassyOS, translated.

Runs Windows programs inside isolated winsecure™ bubbles
on top of Wine, without ever touching the host system.

Components:
  gtranslator     — core launcher / orchestrator
  gtranslator(i)  — executable intelligence (PE scan, installer detection)
  winsecure™      — bubblewrap-based sandbox profiles
"""

__version__ = "0.1.0"

APP_NAME = "gtranslator™"
COMPONENTS = ("gtranslator", "gtranslator(i)", "winsecure™")
