# sshfs-mountctl

> sshfs-mountctl started as a simple bash script that I used constantly — it was janky and ugly but it worked. I have since migrated it to Python with a nice-looking TUI and it has been really useful for me, as I mount and unmount remote folders constantly in my work and lab tasks. Hope it makes things simpler for someone else as well.

A terminal UI for managing persistent SSHFS mounts backed by `systemd --user`.

Built with Python and [Textual](https://github.com/Textualize/textual).

## Features

- Add, edit, clone, remove, enable, disable, and restart SSHFS mounts
- Bulk operations — multi-select mounts for enable / disable / restart / remove
- Browse the remote filesystem over SSH when setting a mount path
- Test SSH connectivity before saving a mount
- View and live-follow `journalctl` logs per mount
- Health check: auto-unmounts stale mounts when the remote goes offline (ping or TCP port check)
- Optional desktop notifications on disconnect / reconnect
- Resolves SSH aliases to real hostnames for health check pings
- Configurable symlink folder and mount root
- Systemd user service per mount — mounts survive reboots and reconnect automatically

## Requirements

- Linux with `systemd --user`
- Python 3.10+
- `textual` Python package
- `sshfs` and `fuse3` / `fusermount3`

### Ubuntu / Debian

```bash
sudo apt install sshfs fuse3
pip install --user textual
```

### Arch Linux

```bash
sudo pacman -S sshfs fuse3
pip install --user textual
```

## Installation

### One-liner

```bash
curl -fsSL https://klick3r.com/sshfs-mountctl | bash
```

> **Always inspect scripts before piping to bash.** You can review the bootstrap script first with `curl -fsSL https://klick3r.com/sshfs-mountctl | less` before running it.

This clones the repo to `~/.local/share/sshfs-mountctl`, installs the package to `~/.local/lib/sshfs-mountctl`, writes the launcher to `~/.bin/sshfs-mountctl`, and sets up the systemd infrastructure.

Re-running the one-liner updates to the latest version.

### Manual

```bash
git clone https://github.com/Klick3r-1/sshfs-manager ~/sshfs-manager
cd ~/sshfs-manager
bash setup.sh
source ~/.profile
```

## Usage

```bash
sshfs-mountctl           # launch the TUI
sshfs-mountctl --debug   # enable debug logging to ~/.local/state/sshfs-mountctl/debug.log
```

### Menu options

| Button | Action |
|--------|--------|
| Add | Add a new mount |
| Edit | Edit an existing mount's configuration |
| Clone | Clone an existing mount as a starting point |
| Remove | Remove a mount |
| Enable | Enable and start a mount (supports multi-select) |
| Disable | Disable and stop a mount (supports multi-select) |
| Restart | Restart a mount (supports multi-select) |
| View logs | Tail `journalctl` logs for a mount |
| Install | Install / repair systemd infrastructure |
| Settings | Configure symlink folder, mount root, and global notifications |

## How it works

Each mount gets a config file at `~/.config/sshfs-mounts/<name>.conf` and a systemd user service instance `sshfs-watchdog@<name>.service`. That service runs `sshfs-watchdog.sh`, which:

- Mounts the SSHFS target on start
- Retries automatically if the mount drops
- Optionally pings the remote host and lazy-unmounts stale mounts when the host goes offline

The service uses `Restart=always` so systemd keeps the watchdog alive across failures and reboots.

## Mount config format

```bash
NAME="media"
REMOTE="user@host:/srv/media"
MOUNTPOINT="/sshfs/media"
RETRY_SECS=120
CONNECT_TIMEOUT=10
SSHFS_OPTS="reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no"
HEALTHCHECK_ENABLED=1
HEALTHCHECK_HOST="192.168.1.10"
HEALTHCHECK_MODE="ping"        # ping or tcp
HEALTHCHECK_PORT=22            # used when mode is tcp
HEALTHCHECK_FAILS=3
PING_TIMEOUT=2
NOTIFICATIONS_ENABLED=0        # also requires global toggle in settings.conf
```

## Files created per mount

For a mount named `media`:

| Path | Purpose |
|------|---------|
| `~/.config/sshfs-mounts/media.conf` | Mount configuration |
| `~/.config/sshfs-mounts/media.mountpoint` | Stored mountpoint path |
| `/sshfs/media` | Mount directory |
| `~/Mounts/media` | Convenience symlink |

## SSH keys

SSH key authentication is required for unattended mounting. The watchdog runs non-interactively and cannot prompt for passwords.

```bash
ssh-keygen -t ed25519
ssh-copy-id user@host
```

An `~/.ssh/config` entry with a `HostName` directive lets you use short aliases in mount configs:

```
Host myserver
    HostName 192.168.1.10
    User myuser
    IdentityFile ~/.ssh/id_ed25519
```

The tool reads `~/.ssh/config` (including `Include` directives) to suggest hosts and resolve aliases to real IPs for health check pings.

## Troubleshooting

```bash
systemctl --user status sshfs-watchdog@<name>.service
journalctl --user -u sshfs-watchdog@<name>.service -n 80 --no-pager
fusermount3 -uz /path/to/mount
```

Or use **View logs** in the TUI to tail logs directly.

## Version history

### v1.0.0 (current)

Built with Python and [Textual](https://github.com/Textualize/textual). Vibecoded with [Claude](https://claude.ai/code).
