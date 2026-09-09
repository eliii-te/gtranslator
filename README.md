# gtranslator™

**Windows apps on GlassyOS — translated, not emulated. No VM. No host access.**

gtranslator™ is a set of three tightly coupled components that let you
double-click a Windows `.exe` and have it run on GlassyOS as if it were
native — while staying completely isolated from the system.

## Components

| Component | Role |
|---|---|
| **gtranslator™** | Core launcher / orchestrator. Splash screen, bubble lifecycle, prefix management. |
| **gtranslator(i)™** | Executable intelligence. Zero-dependency PE scanner: architecture, subsystem, NSIS/Inno/InstallShield/Squirrel installer detection. Decides *installer* vs *portable app*. |
| **winsecure™** | The sandbox. Every Windows app runs inside its own **bubblewrap** bubble — the same isolation primitive Flatpak uses. No host file access, no admin rights, no network (opt-in), private `/tmp`, private PID namespace, private X display. |

**Engine:** Wine. gtranslator™ does not re-implement Wine — it makes Wine
*usable and safe* by wrapping every prefix in a winsecure™ bubble.

## Why not just Wine?

Plain Wine gives Windows programs full access to your system: your files,
your network, your processes. On GlassyOS that is unacceptable. winsecure™
fixes exactly that:

- the app sees an empty filesystem (only `/usr`, `/etc`, `/opt` read-only)
- its `$HOME` is a fresh, per-app directory — not yours
- the executable is mounted read-only at a fixed path
- no host display: the app renders into its own **Xephyr** X server
- the bubble dies with its parent — nothing survives the app closing

## Requirements

```
sudo pacman -S wine-staging xorg-server-xephyr  # bwrap usually present
```

Then check: `gtranslator doctor`

## Usage

```bash
gtranslator info setup.exe        # gtranslator(i)™: is it an installer?
gtranslator run app.exe           # launch portable app in a bubble
gtranslator install setup.exe     # run installer in a bubble
gtranslator run app.exe --network # opt-in network access
gtranslator prefixes list         # list isolated prefixes
gtranslator prefixes remove <id>  # wipe an app + its prefix
gtranslator desktop app.exe       # double-click integration (.desktop)
```

### Double-click integration

```bash
# one-time: register .exe mime type → gtranslator
gtranslator desktop myapp.exe     # creates a launcher entry
```

## How a launch works

1. `gtranslator(i)™` scans the `.exe` (PE header, embedded installer markers).
2. A private X display is started (Xephyr).
3. winsecure™ assembles the bubble: ro-bound system dirs, per-app `$HOME`,
   isolated `WINEPREFIX`, no network.
4. A **"starting with gtranslator™"** splash appears on the host display.
5. Wine boots the app inside the bubble. Splash closes automatically when
   the first app window appears on the isolated display.

## State

Everything lives under `~/.local/share/gtranslator/`:

```
apps/<name>-<hash>/
├── wineprefix/    # isolated Wine prefix (win64/win32 per app)
├── home/          # the app's $HOME inside the bubble
└── exe/           # cached copies of installed executables
```

Remove an app completely: `gtranslator prefixes remove <id>`

## Status

Early development (v0.1). Roadmap:

- [x] gtranslator(i)™ PE scanner + installer detection
- [x] winsecure™ bubblewrap profiles (no net, no host fs, private display)
- [x] Xephyr display isolation + splash
- [ ] post-install app discovery (`gtranslator install` → find installed exe)
- [ ] Wine-gecko/mono bundling for MSI-free installers
- [ ] audio (pipewire null-sink per bubble)
- [ ] .exe mime-type auto-registration
- [ ] GlassyOS desktop integration (file manager "open with gtranslator™")

## License

MIT
