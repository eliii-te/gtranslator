# gtranslator™

### Windows software on GlassyOS — *translated, not emulated.*

**Click a Windows `.exe`. It runs — isolated, invisible to the system, with its own
private Windows world. No VM. No terminal. No host access. Ever.**

gtranslator™ is the Windows-translator for GlassyOS: a security-first runtime that
takes Windows programs and makes them speak GlassyOS — while making them believe
they never left Windows.

> **Why "translator"?** An emulator pretends to be another machine. A translator
> keeps both worlds intact: the program speaks Windows fluently, the system stays
> GlassyOS. Nothing is faked at the hardware level — the *boundaries* are real.

---

## The revolution in one paragraph

For 30 years, running Windows software on Linux meant one of two things:
**Wine** — which gives every program *full access to your system* (files, network,
processes, everything), or **a VM** — which means carrying a second operating
system around. gtranslator™ rejects both trade-offs. It runs Windows programs
through the Wine *engine*, but wraps every single launch in a **winsecure™ bubble**:
an isolated, disposable world with no host files, no host network, no admin
rights, no background — plus a display of its own. The result: Windows programs,
*without* the Windows threat model.

---

## The three components

### gtranslator™ — the orchestrator
Double-click a `.exe` and gtranslator™ takes over:
1. **gtranslator(i)™** analyses the file (PE header, installer fingerprints).
2. A **winsecure™ bubble** is assembled — an empty, private world.
3. An animated splash appears: *"starting … with gtranslator™"*.
4. The program runs in its isolated display — fullscreen, like a native app.
5. On the first successful run, the `.exe` becomes a **`.gwp`** — and from then
   on, it starts instantly with its stored setup.

### winsecure™ — the sandbox
Every Windows program runs in its own **bubble** (bubblewrap — the same primitive
Flatpak uses, hardened further):

| Threat | Verdict |
|---|---|
| Host filesystem | **denied** — the app sees an empty world (only `/usr` read-only) |
| Your home directory | **denied** — the app gets a fresh, per-app `$HOME` |
| SSH keys, documents, photos | **denied** — physically not mounted |
| Network | **denied by default** — opt-in per launch, with a user prompt |
| Root / admin | **denied** — impossible by construction |
| Background activity | **denied** — the bubble dies with its parent |
| Host display | **denied** — the app renders into its own isolated X display |
| Other apps' data | **denied** — every app gets its own prefix, its own world |

The app's entire "C:\ drive" is a disposable folder under
`~/.local/share/gtranslator/`. Remove the app → everything it ever wrote is gone.

### gtranslator(i)™ — the intelligence
Zero-dependency executable scanner:
- PE/PE32+ parsing — architecture, subsystem, sections
- Installer fingerprinting — NSIS, Inno Setup, InstallShield, Squirrel, WiX
- **Post-install discovery** — after an installer runs, snapshot-diffing finds the
  program that was actually installed (even in `C:\7-Zip` instead of
  `Program Files`), ignoring Wine's own built-ins (wordpad, IE, …)
- Decides: *installer* → run and discover · *portable app* → run and convert

---

## The .gwp format — Glassy-Windows-Program

After its first successful run, a Windows `.exe` is **converted into a `.gwp`**:
a single-file container (ZIP) holding:

```
myapp.gwp
├── gwp.json          # the app's whole setup + permission manifest
└── payload/          # the original executable (portable apps)
```

The manifest stores everything needed to start **instantly** on the next
double-click: prefix ID, architecture, start target, permissions, run statistics.
No re-scanning, no re-setup.

`.gwp` files are first-class GlassyOS citizens:
- they appear in the **app launcher** with a clean name
- they carry a **permission profile** (rights pyramid, top level: root never,
  background never, network ask-first)
- their data lives in a **visible folder** — `~/gtranslator/<App>/` — with the
  Windows profile layout (AppData, Documents, Downloads, …), so users can see and
  manage exactly what their Windows apps write

```
~/gtranslator/7-Zip/
├── AppData/Local · AppData/Roaming · AppData/LocalLow
├── Desktop · Documents · Downloads · Music · Pictures · Videos
└── … (the app believes this is C:\Users\you)
```

---

## Why this is different

| | Plain Wine | VM | **gtranslator™** |
|---|---|---|---|
| Windows program can read your files | **yes — all of them** | no | **no — none** |
| Windows program can touch your network | **yes** | yes (NAT) | no (opt-in) |
| Needs a second OS install | no | **yes (20+ GB)** | no |
| App appears as a normal window | yes | inside a VM screen | **yes** |
| Double-click `.exe` → it runs | setup required | setup required | **yes** |
| Per-app state, removable | no | no | **yes (`.gwp`)** |
| Boot time | instant | 30–60 s | **instant** |

**gtranslator™ is what Wine would look like if it had been designed for a
security-first OS from day one.**

---

## Requirements & install

GlassyOS (Arch-based). PIN-protected installer:

```bash
curl -sL https://github.com/eliii-te/gtranslator/raw/main/install.sh | bash
# → prompts for the installation PIN
```

Or manually: `sudo pacman -S wine-staging bubblewrap xorg-server-xephyr openbox`,
clone this repo, run `python3 -m gtranslator doctor`.

## Usage

```bash
gtranslator doctor                  # environment check
gtranslator run app.exe             # launch (double-click handler)
gtranslator install setup.exe       # run an installer, discover the app
gtranslator info file.exe|.gwp      # gtranslator(i)™ analysis
gtranslator prefixes list|remove    # manage app state
gtranslator desktop app.exe         # add to app launcher
```

That's it. Double-clicking a `.exe` or `.gwp` in the file manager does the rest.

## Status — Alpha v0.2

Working end-to-end: bubble isolation, splash, .gwp conversion with snapshot
discovery, launcher entries, visible user-data folders, mime registration,
Hyprland integration, PIN-protected installer.

**Roadmap**

- [x] gtranslator(i)™ PE scanner + installer detection
- [x] winsecure™ bubbles (no fs, no net, private display, die-with-parent)
- [x] .gwp format + post-install discovery (snapshot-diff)
- [x] visible Windows-profile data folders (`~/gtranslator/<App>`)
- [x] Hyprland window integration (centered, focused)
- [x] PIN-protected GlassyOS installer
- [ ] **Mini-VM fallback engine** — Wine-first, VM for everything Wine can't run
- [ ] audio (isolated per-app sink)
- [ ] icon extraction for launcher entries
- [ ] .gwp → "repair/reinstall" flow

## License

MIT — © 2026 Eli / GlassyOS
