#!/usr/bin/env bash
# setup.sh — install sshfs-mountctl for the current user
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BIN_DIR="$HOME/.bin"
LIB_DIR="$HOME/.local/lib/sshfs-mountctl"
CFG_DIR="$HOME/.config/sshfs-mounts"
SYSTEMD_DIR="$HOME/.config/systemd/user"
MOUNTS_DIR="$HOME/Mounts"
UNIT="$SYSTEMD_DIR/sshfs-watchdog@.service"
WATCHDOG_DST="$BIN_DIR/sshfs-watchdog.sh"
LAUNCHER="$BIN_DIR/sshfs-mountctl"
MOUNT_ROOT="/sshfs"

# ── Helpers ──────────────────────────────────────────────────────────────────

ok()   { printf '  \033[32m✓\033[0m  %s\n' "$*"; }
info() { printf '  \033[34m·\033[0m  %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m  %s\n' "$*"; }
err()  { printf '  \033[31m✗\033[0m  %s\n' "$*" >&2; }
die()  { err "$*"; exit 1; }

# ── Preflight ────────────────────────────────────────────────────────────────

echo ""
echo "sshfs-mountctl installer"
echo "========================"
echo ""

info "Checking dependencies…"

command -v python3 >/dev/null 2>&1 || die "python3 not found — install it first"
ok "python3 found: $(python3 --version)"

command -v sshfs >/dev/null 2>&1 || warn "sshfs not found — mounts won't work until installed"
command -v fusermount3 >/dev/null 2>&1 || \
  command -v fusermount >/dev/null 2>&1  || \
  warn "fusermount3 not found — unmounting may fail"

python3 -c "import textual" 2>/dev/null \
  || die "textual not installed — run: pip install --user textual"
ok "textual found: $(python3 -c 'import textual; print(textual.__version__)')"

echo ""

# ── Path configuration ────────────────────────────────────────────────────────

# Load existing settings if present so re-runs show current values as defaults
SETTINGS_CONF="$CFG_DIR/settings.conf"
if [[ -f "$SETTINGS_CONF" ]]; then
  # shellcheck disable=SC1090
  source "$SETTINGS_CONF"
  MOUNT_ROOT="${MOUNT_ROOT:-/sshfs}"
  LOCAL_LINK_DIR="${LOCAL_LINK_DIR:-${HOME}/Mounts}"
fi

echo "Configure paths  (press Enter to accept the default)"
echo ""

read -rp "  Mount root  [${MOUNT_ROOT}]: " input_mount_root
[[ -n "$input_mount_root" ]] && MOUNT_ROOT="$input_mount_root"

read -rp "  Symlink folder  [${MOUNTS_DIR}]: " input_link_dir
[[ -n "$input_link_dir" ]] && MOUNTS_DIR="$input_link_dir"

echo ""

# ── Directories ──────────────────────────────────────────────────────────────

info "Creating directories…"
mkdir -p "$BIN_DIR" "$LIB_DIR" "$CFG_DIR" "$SYSTEMD_DIR" "$MOUNTS_DIR"
ok "~/.bin, ~/.local/lib/sshfs-mountctl, ~/.config/sshfs-mounts, $MOUNTS_DIR"

# Write settings.conf so the TUI and watchdog pick up the chosen paths
info "Writing settings.conf…"
mkdir -p "$CFG_DIR"
cat > "$SETTINGS_CONF" <<EOF
LOCAL_LINK_DIR="${MOUNTS_DIR}"
MOUNT_ROOT="${MOUNT_ROOT}"
NOTIFICATIONS_ENABLED=0
EOF
ok "$SETTINGS_CONF"

# ── Copy package ─────────────────────────────────────────────────────────────

info "Installing package to $LIB_DIR…"
cp -r "$REPO_DIR/sshfs_mountctl" "$LIB_DIR/"
cp "$REPO_DIR/sshfs-watchdog.sh" "$LIB_DIR/"
# Remove bytecode so stale .pyc files from the repo don't carry over
find "$LIB_DIR" -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
find "$LIB_DIR" -name '*.pyc' -delete 2>/dev/null || true
ok "package copied"

# ── Launcher ─────────────────────────────────────────────────────────────────

info "Writing launcher to $LAUNCHER…"
cat > "$LAUNCHER" <<EOF
#!/usr/bin/env python3
import sys, os
sys.path.insert(0, os.path.expanduser("~/.local/lib/sshfs-mountctl"))
try:
    from sshfs_mountctl.__main__ import main
except ImportError as exc:
    print(f"Error: {exc}")
    print("Re-run setup.sh to reinstall.")
    sys.exit(1)
main()
EOF
chmod +x "$LAUNCHER"
ok "launcher written and executable"

# ── Watchdog ─────────────────────────────────────────────────────────────────

info "Installing watchdog script…"
cp "$REPO_DIR/sshfs-watchdog.sh" "$WATCHDOG_DST"
chmod +x "$WATCHDOG_DST"
ok "$WATCHDOG_DST"

# ── Systemd unit template ────────────────────────────────────────────────────

info "Writing systemd unit template…"
cat > "$UNIT" <<'EOF'
[Unit]
Description=SSHFS watchdog mount for %i
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart=%h/.bin/sshfs-watchdog.sh %h/.config/sshfs-mounts/%i.conf
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
EOF
ok "$UNIT"

systemctl --user daemon-reload 2>/dev/null && ok "systemd user daemon reloaded" \
  || warn "Could not reload systemd user daemon (running without systemd?)"

# ── /sshfs mount root ────────────────────────────────────────────────────────

if [[ ! -d "$MOUNT_ROOT" ]]; then
    info "Creating $MOUNT_ROOT (requires sudo)…"
    if sudo mkdir -p "$MOUNT_ROOT" \
        && sudo chown "$(id -un):$(id -gn)" "$MOUNT_ROOT" \
        && sudo chmod 755 "$MOUNT_ROOT"; then
        ok "$MOUNT_ROOT created and owned by $(id -un)"
    else
        warn "Could not create $MOUNT_ROOT — create it manually: sudo mkdir -p $MOUNT_ROOT && sudo chown $(id -un) $MOUNT_ROOT"
    fi
else
    ok "$MOUNT_ROOT already exists"
fi

# ── PATH ─────────────────────────────────────────────────────────────────────

MARKER="# Added by sshfs-mountctl installer"
EXPORT='export PATH="$HOME/.bin:$PATH"'

add_to_path() {
    local file="$1"
    if [[ -f "$file" ]] && grep -qF "$MARKER" "$file"; then
        info "PATH already set in $file"
        return
    fi
    printf '\n%s\n%s\n' "$MARKER" "$EXPORT" >> "$file"
    ok "added ~/.bin to PATH in $file"
}

add_to_path "$HOME/.profile"
SHELL_NAME="$(basename "${SHELL:-}")"
case "$SHELL_NAME" in
    bash) add_to_path "$HOME/.bashrc" ;;
    zsh)  add_to_path "$HOME/.zshrc"  ;;
    fish)
        FISH_CFG="$HOME/.config/fish/config.fish"
        mkdir -p "$(dirname "$FISH_CFG")"
        touch "$FISH_CFG"
        if ! grep -qF "fish_add_path \$HOME/.bin" "$FISH_CFG"; then
            printf '\n%s\nfish_add_path $HOME/.bin\n' "$MARKER" >> "$FISH_CFG"
            ok "added ~/.bin to PATH in $FISH_CFG"
        else
            info "PATH already set in $FISH_CFG"
        fi
        ;;
esac

# ── Done ─────────────────────────────────────────────────────────────────────

echo ""
echo "Installation complete."
echo ""
echo "  Reload your shell or run:  source ~/.profile"
echo "  Then launch with:          sshfs-mountctl"
echo ""
