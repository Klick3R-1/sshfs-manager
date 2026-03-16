"""Path constants and static configuration shared across all modules."""

from __future__ import annotations

from pathlib import Path

HOME           = Path.home()
MOUNTS_DIR     = HOME / ".config" / "sshfs-mounts"
SYSTEMD_DIR    = HOME / ".config" / "systemd" / "user"
UNIT_TEMPLATE  = SYSTEMD_DIR / "sshfs-watchdog@.service"
WATCHDOG_DST   = HOME / ".bin" / "sshfs-watchdog.sh"
LOCAL_LINK_DIR = HOME / "Mounts"
MOUNT_ROOT     = Path("/sshfs")
SCRIPT_DIR     = Path(__file__).resolve().parent.parent   # repo root
WATCHDOG_SRC   = SCRIPT_DIR / "sshfs-watchdog.sh"
LOG_FILE       = HOME / ".local" / "state" / "sshfs-mountctl" / "debug.log"

EDITOR_CANDIDATES = ["micro", "nano", "vim", "vi", "nvim", "emacs", "hx"]

UNIT_TEMPLATE_CONTENT = """\
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
"""
