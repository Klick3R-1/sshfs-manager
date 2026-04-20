"""Path constants and static configuration shared across all modules."""

from __future__ import annotations

import sys
from pathlib import Path

HOME           = Path.home()
MOUNTS_DIR     = HOME / ".config" / "sshfs-mounts"
SYSTEMD_DIR    = HOME / ".config" / "systemd" / "user"
UNIT_TEMPLATE  = SYSTEMD_DIR / "sshfs-watchdog@.service"
WATCHDOG_DST        = HOME / ".bin" / "sshfs-watchdog.sh"
WATCHDOG_SYSTEM_DST = Path("/usr/lib/sshfs-mountctl/sshfs-watchdog.sh")
LOCAL_LINK_DIR = HOME / "Mounts"
MOUNT_ROOT     = Path("/sshfs")
# When running as a PyInstaller bundle, files are extracted to sys._MEIPASS
SCRIPT_DIR     = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
WATCHDOG_SRC   = SCRIPT_DIR / "sshfs-watchdog.sh"
LOG_FILE       = HOME / ".local" / "state" / "sshfs-mountctl" / "debug.log"

EDITOR_CANDIDATES = ["micro", "nano", "vim", "vi", "nvim", "emacs", "hx"]

GITHUB_RELEASES_URL = "https://api.github.com/repos/Klick3r-1/sshfs-manager/releases/latest"
UPDATE_CACHE_FILE   = HOME / ".local" / "state" / "sshfs-mountctl" / "update_check.json"

def _watchdog_path() -> str:
    """Return the watchdog script path — system install takes priority over user install."""
    if WATCHDOG_SYSTEM_DST.exists():
        return str(WATCHDOG_SYSTEM_DST)
    return "%h/.bin/sshfs-watchdog.sh"


def make_unit_template_content() -> str:
    return f"""\
[Unit]
Description=SSHFS watchdog mount for %i
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
ExecStart={_watchdog_path()} %h/.config/sshfs-mounts/%i.conf
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
"""


UNIT_TEMPLATE_CONTENT = make_unit_template_content()
