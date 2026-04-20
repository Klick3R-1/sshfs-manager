![sshfs-mountctl main window](sshfs-mainWindow.png)
 
# sshfs-mountctl

> sshfs-mountctl started as a simple bash script that I used constantly — it was janky and ugly but it worked. I have since migrated it to Python with a nice-looking TUI and it has been really useful for me, as I mount and unmount remote folders constantly in my work and lab tasks. Hope it makes things simpler for someone else as well.

A terminal UI for managing persistent SSHFS mounts backed by `systemd --user`.

Built with Python and [Textual](https://github.com/Textualize/textual).

## Features

- Add, edit, clone, remove, enable, disable, and restart SSHFS mounts
- Bulk operations — multi-select mounts for enable / disable / restart / remove
- Mount groups — organize mounts into named groups, enable/disable a whole group at once
- Command line flags for scripting: `--enable`, `--disable`, `--list`, `--status`, and group variants
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
- `sshfs` and `fuse3` / `fusermount3`

## Installation

### Arch Linux

Install from the AUR — dependencies are handled automatically:

```bash
yay -S sshfs-mountctl
```

Then run first-time setup:

```bash
sshfs-mountctl --init
```

This creates the required directories, writes your settings, and sets up `/sshfs` (the default mount root) with sudo.

### Other Linux — one-liner

```bash
curl -fsSL https://klick3r.com/sshfs-manager | bash
```

Installs `textual` if missing, copies the package, writes the launcher to `~/.bin/sshfs-mountctl`, and sets up all systemd infrastructure. Re-running updates to the latest version.

> **Always inspect scripts before piping to bash.**
> Preview first: `curl -fsSL https://klick3r.com/sshfs-manager | less`

After install, reload your shell or run `source ~/.profile`, then launch with `sshfs-mountctl`.

### From source

```bash
git clone https://github.com/Klick3r-1/sshfs-manager ~/sshfs-manager
cd ~/sshfs-manager
pip install --user textual
bash setup.sh
source ~/.profile
```

### Binary release

Download the latest `sshfs-mountctl` binary from the [Releases](https://github.com/Klick3r-1/sshfs-manager/releases) page — bundles Python and all dependencies, no install needed.

```bash
chmod +x sshfs-mountctl
./sshfs-mountctl
```

On first launch the install prompt appears automatically.

## Uninstallation

### AUR

```bash
sudo pacman -R sshfs-mountctl
```

This removes the package but leaves your mount configs at `~/.config/sshfs-mounts/` untouched.

### One-liner / from source

Open the app and go to **Install → Uninstall**. You will be asked whether to keep or delete your mount configs. The app removes all systemd units, the watchdog script, the launcher, and the installed package, then exits.

## Usage

```bash
sshfs-mountctl           # launch the TUI
sshfs-mountctl --init    # first-time setup
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
| Settings | Configure symlink folder, mount root, and global notifications |

### CLI flags

The tool can be scripted without opening the TUI:

| Flag | Description |
|------|-------------|
| `--list` | List all mounts with status |
| `--status NAME` | Show status for a single mount |
| `--enable NAME` | Enable and start a mount |
| `--disable NAME` | Stop and disable a mount |
| `--list-groups` | List all group names |
| `--list-group GROUP` | List mounts in a group with status |
| `--enable-group GROUP` | Enable all mounts in a group |
| `--disable-group GROUP` | Disable all mounts in a group |

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

## Roadmap

### Planned
- **Click row to edit** — click a mount in the table to open its config directly
- **Export / import configs** — backup and restore all mount configs as a single archive
- **Changelog modal** — show release notes once when a new version is detected
- **Auto-reconnect indicator** — distinguish "service active, waiting to reconnect" from "mounted and healthy" in the status table
- **Post-connect / pre-disconnect hooks** — per-mount `ON_CONNECT` / `ON_DISCONNECT` shell commands in the config, fired by the watchdog

### Thinking about it
- **SSH key setup** — a guided `ssh-copy-id` flow inside the app

  This one sits on the backburner deliberately. SSH key management is a sensitive security operation, and there is real value in users understanding what they are doing when they set it up — not just clicking through a wizard. Good security hygiene means knowing the tools, not just trusting them.

  That is also why sshfs-mountctl intentionally has no password support: storing SSH credentials would make the tool responsible for securing them, which is a responsibility that does not belong here. The right place for key management is the user, their terminal, and `ssh-keygen` / `ssh-copy-id`.

  Until I can come up with a secure and transparent way to both generate keys and ensure they are stored safely — with the user fully understanding what is happening at each step — this feature will intentionally stay hanging.

## Version history

### v1.1.2 (current)

- Add `--init` flag for first-time setup without opening the TUI — creates directories, prompts for mount root and symlink folder, writes settings, handles `/sshfs` creation with sudo

### v1.1.1

- AUR / system install support — Install button and status label are hidden when the watchdog is installed system-wide (e.g. via AUR package)

See [CHANGELOG.md](CHANGELOG.md) for full history.
