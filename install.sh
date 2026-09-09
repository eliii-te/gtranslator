#!/usr/bin/env bash
# =============================================================================
#  gtranslator™ — GlassyOS Windows-Translator · Alpha v0.2 Installer
#
#  Exklusiv für GlassyOS. Installiert:
#    · Wine-Engine + Isolation-Tools (wine-staging, bubblewrap, Xephyr, openbox)
#    · gtranslator™ nach /opt/gtranslator
#    · Startbefehl: gtranslator
#    · .exe/.gwp-Doppelklick-Registrierung (mime)
#
#  Der Installer ist PIN-geschützt. Die PIN ist NICHT im Klartext in dieser
#  Datei — nur ein SHA-256-Fingerabdruck (Lookup nicht trivial möglich).
# =============================================================================
set -euo pipefail

# SHA-256 der Installations-PIN (6-stellig, vom Maintainer vergeben)
PIN_HASH="12b8c3e83e9715b683d35fbc4fbb0157490cc592a0d5123faf0b63d18f917e65"
REPO_URL="https://github.com/eliii-te/gtranslator.git"
INSTALL_DIR="/opt/gtranslator"
VERSION="0.2.0-alpha"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

say()  { printf "${GREEN}==${NC} %s\n" "$*"; }
warn() { printf "${YELLOW}!!${NC} %s\n" "$*"; }
die()  { printf "${RED}XX${NC} %s\n" "$*"; exit 1; }

echo
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║         gtranslator™  ·  Alpha ${VERSION}        ║"
echo "  ║      Windows-Programme auf GlassyOS —         ║"
echo "  ║      übersetzt, isoliert, ohne VM-Gefühl      ║"
echo "  ╚══════════════════════════════════════════════╝"
echo

# --------------------------------------------------------------------------
# 1) PIN-Abfrage
# --------------------------------------------------------------------------
for attempt in 1 2 3; do
    read -rsp "  Installations-PIN (6 Stellen) eingeben: " pin
    echo
    hash=$(printf '%s' "$pin" | sha256sum | awk '{print $1}')
    if [ "$hash" = "$PIN_HASH" ]; then
        say "PIN korrekt — Installation wird gestartet."
        break
    fi
    if [ "$attempt" -lt 3 ]; then
        warn "Falsche PIN. Noch ${attempt}/3 Versuche übrig."
    else
        die "PIN dreimal falsch. Installation abgebrochen."
    fi
done

# --------------------------------------------------------------------------
# 2) Systempakete (nur wenn fehlend)
# --------------------------------------------------------------------------
say "Prüfe/installiere Systempakete …"
for pkg in wine-staging bubblewrap xorg-server-xephyr openbox; do
    if pacman -Q "$pkg" &>/dev/null; then
        say "  ✓ $pkg bereits installiert"
    else
        warn "  installiere $pkg …"
        sudo pacman -S --needed --noconfirm "$pkg" || die "Paket $pkg konnte nicht installiert werden"
    fi
done

# tkinter für Splash & Dialoge
if ! python3 -c "import tkinter" &>/dev/null; then
    warn "installiere python tk …"
    sudo pacman -S --needed --noconfirm tk || warn "tk fehlt — Splash fällt auf Konsolen-Modus zurück"
fi

# --------------------------------------------------------------------------
# 3) gtranslator™ nach /opt/gtranslator
# --------------------------------------------------------------------------
say "Installiere gtranslator™ nach ${INSTALL_DIR} …"
if [ -d "${INSTALL_DIR}/.git" ]; then
    sudo git -C "$INSTALL_DIR" pull --ff-only -q || true
else
    sudo rm -rf "$INSTALL_DIR"
    sudo git clone -q --depth 1 "$REPO_URL" "$INSTALL_DIR" || die "Clone fehlgeschlagen"
fi
sudo chown -R root:root "$INSTALL_DIR"
sudo rm -rf "$INSTALL_DIR"/gtranslator/__pycache__

# --------------------------------------------------------------------------
# 4) Startbefehl
# --------------------------------------------------------------------------
say "Lege Startbefehl an (/usr/local/bin/gtranslator) …"
sudo tee /usr/local/bin/gtranslator > /dev/null << 'EOF'
#!/usr/bin/env bash
exec env PYTHONPATH="/opt/gtranslator" python3 -m gtranslator "$@"
EOF
sudo chmod +x /usr/local/bin/gtranslator

# --------------------------------------------------------------------------
# 5) Doppelklick-Registrierung (.exe/.gwp) + Umgebungs-Check
# --------------------------------------------------------------------------
say "Registriere .exe/.gwp-Doppelklick …"
gtranslator mime register || warn "Mime-Registrierung fehlgeschlagen (Desktop neu laden?)"

# --------------------------------------------------------------------------
# 6) Hyprland-Regel (Xephyr-Fenster zentrieren)
# --------------------------------------------------------------------------
HRULES="$HOME/.config/hypr/UserConfigs/WindowRules.conf"
if [ -f "$HRULES" ] && ! grep -q "gtranslator" "$HRULES"; then
    say "Ergänze Hyprland-Regel (Xephyr zentrieren) …"
    cat >> "$HRULES" << 'EOF'

# gtranslator™ — center the isolated display window
windowrule = match:class ^(Xephyr)$, center on
EOF
    if command -v hyprctl &>/dev/null; then
        SIG=$(ls /run/user/$(id -u)/hypr/ 2>/dev/null | head -1 || true)
        [ -n "$SIG" ] && HYPRLAND_INSTANCE_SIGNATURE="$SIG" hyprctl reload &>/dev/null || true
    fi
fi

# --------------------------------------------------------------------------
# 7) Fertig
# --------------------------------------------------------------------------
echo
say "gtranslator™ ${VERSION} installiert! 🎉"
echo
echo "  Nächste Schritte:"
echo "   · Terminal:   gtranslator doctor   → Umgebung prüfen"
echo "   · Nutzung:    gtranslator run <app.exe>  (oder einfach Doppelklick)"
echo "   · App-Daten:  ~/gtranslator/<AppName>/  (Windows-Profil sichtbar)"
echo
