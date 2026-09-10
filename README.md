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

GlassyOS (Arch-based). Installer:

```bash
curl -sL https://github.com/eliii-te/gtranslator/raw/main/install.sh | bash
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

## gtranslator™ emu — *next version, in development*

> ⚠️ **Not released yet.** Everything below describes what is coming in the
> **next version**. The implementation is still in development and is **not**
> part of this repository yet — this document is published *ahead of the code*
> on purpose.

**gtranslator™ emu is the second engine of gtranslator™ — and probably the
biggest half of it.** Where the default engine *translates* Windows for
GlassyOS (Wine inside a winsecure™ bubble), emu stops translating and simply
gives the program a **real, tiny, disposable Windows** to live in.

It exists because a whole class of software cannot be translated at all.

### Why emu exists

Wine is astonishing — but some programs are built to *detect* it, or depend on
parts of Windows Wine will never faithfully provide. In practice this is the
**browser & messenger class**: Chrome, Edge, Firefox, Opera, Brave, WhatsApp,
Telegram, Signal, Discord, Slack, Zoom, Teams, and the installers that ship
them. We tested this to death: Chrome's installer aborts with *SETUP ERROR:
INVALID OPTION*, Edge refuses to install no matter how convincingly we fake the
registry, Firefox dies with `EXCEPTION_ACCESS_VIOLATION`, Telegram's installer
crashes. That is not a bug to fix — it is the boundary of translation.

So for exactly those apps, gtranslator™ stops pretending and starts a machine.

### What emu is

- **A deeply trimmed Windows 10 Pro** running in a **single file** — a
  `windows.qcow2` of roughly **11 GB**. Not a fresh Windows install: a Windows
  that has been stripped down to just what it takes to run apps.
- **Started on demand** by `qemu` with KVM, headless, in the background.
- **Presented like a normal app**: gtranslator™ brings its own display client,
  so the Windows window is just a window on your desktop — no “pick a VM app,
  boot it, connect to it” ceremony.
- **Disposable by design**: one file. Trash it, copy it, back it up, hand it to
  someone else. No driver games, no snapshots of your real machine.

### The image — how small can Windows get?

The base image is not “Windows minimal by hope” — it is measured. On first boot
a script takes Windows apart:

- **Every Store/UWP app removed** (all users + provisioned) — only the shared
  runtime frameworks (VCLibs, .NET Native, UI.Xaml) stay, because apps link
  against them.
- **Microsoft Edge, EdgeUpdate and the elevation service removed.**
- **~17 optional Windows features removed** — Internet Explorer, Windows Media
  Player, XPS/Fax printing, Hello Face, Math Recognizer, PowerShell v2, …
- **~50 services disabled** — diagnostics, telemetry (`DiagTrack`), Xbox, Search
  indexing, Bluetooth, Print Spooler, Windows Update, Defender, SysMain, and the
  rest of the background noise that exists to talk to Microsoft, not to run your
  program.
- **Telemetry, Defender and Windows Update switched off at policy level**, and
  their scheduled tasks deleted.
- **Hibernation off** (kills `hiberfil.sys`), **Reserved Storage off** (~7 GB
  that Windows otherwise keeps for itself), **System Restore off**.
- **Pagefile shrunk** to 1–2 GB, **WinSxS component store compacted**
  (`resetbase`) and the whole OS written in **CompactOS** mode (system files
  stored compressed).
- Caches, logs, Panther, Prefetch, `Windows.old`, the update cache — gone.

Result: a Windows 10 **Pro** that occupies roughly **8 GB on disk** inside a
40 GB virtual disk, boots headless in seconds, and idles with a fraction of the
processes of a normal install.

### Architecture

**1. The host orchestrator (`gtranslator emu …`)**
qemu is started with KVM, a single IDE disk, a USB tablet (so the guest has an
*absolute* pointer — essential for a remote display to feel right), an
`e1000` NIC on QEMU's user-mode network, a VNC server bound to `127.0.0.1`
only, and a QEMU monitor socket for clean control (graceful ACPI shutdown, etc.).
The VM can run in the background and be reused across apps — starting a second
app doesn't reboot Windows.

**2. The display — gtranslator™'s own VNC client**
There is no `virt-viewer`, no `remote-viewer`, no SPICE: gtranslator™ ships a
**self-contained VNC/RFB viewer written in pure Python + tkinter**. It speaks
RFB 3.8, forces a known pixel format, decodes RAW updates straight into a
framebuffer, encodes it to PNG with stdlib `zlib`, hands it to Tk as base64, and
forwards mouse/keyboard back into the guest. No dependencies, no root, nothing
to install — and it only repaints when the guest actually changes pixels.
*(A real bug this solved: Tk strings terminate at NUL bytes, so passing a raw
binary image got truncated — hence the PNG/base64 path.)*

**3. The file channel — HTTP, not SMB**
Getting the `.exe` *into* the VM is done over a tiny private HTTP server on the
host (`127.0.0.1:8899`). QEMU's user-mode networking maps the host loopback to
`10.0.2.2` inside the guest, so Windows just fetches `http://10.0.2.2:8899/…`
with built-in tooling. This matters: QEMU's own SMB share needs `smbd` (Samba)
on the host, and virtio-fs needs Windows drivers — HTTP needs neither. There is
nothing to install, on either side. The transfer is one-shot: a `run.cmd`
written by the host is served exactly once and deleted, so the guest can never
re-run a stale command.

**4. The guest side — a tiny watcher**
Inside Windows a single scheduled task (`gtranslator-watcher`) polls the shared
channel once a minute, downloads the pending `run.cmd`, executes it, and
signals completion back to the host. It runs **as the logged-in user, elevated**
— logged-in so the app window appears on the real desktop (not in an invisible
session-0), elevated so installers don't stall on a UAC prompt nobody can click.
Apps are launched **maximised**, so they fill the window like a native app.

**5. The loading screen — the emu pulse**
Starting emu is not instant (a VM has to come up), so gtranslator™ shows the
**same loader you know from the Wine path** — same window, same type, same ring
spinner — except the accent colour **pulses through every hue** while it waits.
It disappears the moment the guest reports the app is up, so you're never
looking at a blank frame. The hand-off is: loader on → VM (boots if needed) →
app handed over → guest launches it → guest signals back → loader off → window.

### Two engines, one click

gtranslator™ picks the engine for you:

- **Automatic routing** — point `gtranslator run` at a browser, a messenger or
  their installer and it goes to **emu**; everything else goes through Wine.
- **`--emu` / `--wine`** — force either engine when you know better.
- **“switch to gtranslator emu”** — a button right in the loader. If the Wine
  path isn't working for some program, one click tears the bubble down and
  re-runs the same app in the VM. No re-downloading, no re-configuring.

### CLI

```
gtranslator emu init [--disk PATH] [--from IMG]   register / set up the VM image
gtranslator emu start [--headless]                boot it (and show it)
gtranslator emu stop                              graceful shutdown
gtranslator emu status                            state, disk, share, display
gtranslator emu view                              open the VM window
gtranslator emu run <app.exe> [--args …]          hand an app into the VM
gtranslator emu share [DIR]                       show / set the shared folder
gtranslator emu setup-guest                       prepare the guest watcher
```

### Design notes & trade-offs

- Why not plain **SMB**? Needs a Samba server on the host. HTTP is free.
- Why not **SPICE**? Lovely — but it needs a QEMU built with SPICE and a client;
  neither is guaranteed. A built-in VNC client always works.
- Why not **virtio-fs / 9p**? Windows needs extra drivers. HTTP needs none.
- Why **VNC on loopback only**? It never leaves the machine; there is no remote
  attack surface.
- Why a **real Windows** and not a “minimal Windows clone”? Because the apps
  that need emu are exactly the ones that refuse to run anywhere but real,
  unmodified Windows.

### Security model

emu is a **second, separate machine** — not a wrapped process. Whatever a
program does inside it, it does to a disposable file, not to GlassyOS: it can't
see your files, your processes or your network beyond the one shared channel
you opened. And because the whole VM is one file, “nuke it from orbit” is a
single `rm` — then re-provision from the published image.

### Status

🚧 **In development.** The image, the orchestrator, the viewer, the file channel
and the guest watcher all exist and run; hardening, polish and packaging are
ongoing. Nothing described here is in the current alpha release — the
implementation files will land together with the next version.

## Status — Alpha v0.2

Working end-to-end: bubble isolation, splash, .gwp conversion with snapshot
discovery, launcher entries, visible user-data folders, mime registration,
Hyprland integration, GlassyOS installer.

**Roadmap**

- [x] gtranslator(i)™ PE scanner + installer detection
- [x] winsecure™ bubbles (no fs, no net, private display, die-with-parent)
- [x] .gwp format + post-install discovery (snapshot-diff)
- [x] visible Windows-profile data folders (`~/gtranslator/<App>`)
- [x] Hyprland window integration (centered, focused)
- [x] GlassyOS installer
- [ ] **Mini-VM fallback engine** — Wine-first, VM for everything Wine can't run  *(gtranslator™ emu — in development, see above)*
- [ ] audio (isolated per-app sink)
- [ ] icon extraction for launcher entries
- [ ] .gwp → "repair/reinstall" flow

## License

MIT — © 2026 Eli / GlassyOS
