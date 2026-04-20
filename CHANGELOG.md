# Changelog

## v1.1.2 (current)

- Add `--init` flag for first-time setup without opening the TUI — creates directories, prompts for mount root and symlink folder, writes settings, handles `/sshfs` creation with sudo

## v1.1.1

- AUR / system install support — Install button and status label are hidden when the watchdog is installed system-wide (e.g. via AUR package)

## v1.1.0

- Mount groups — assign mounts to named groups (e.g. "work", "media") and enable/disable the whole group at once
- Group management in the app: create, rename, delete groups and manage which mounts belong to each
- Groups section added to the main menu with Enable, Disable, Edit, and Members buttons
- Command line flags for scripting without opening the app: `--enable`, `--disable`, `--list`, `--status`, `--enable-group`, `--disable-group`, `--list-group`, `--list-groups`
- Mount table now shows the group for each mount

## v1.0.2

- Version moved to subtitle; title simplified to "SSHFS Mount Control"
- Startup checks GitHub releases once per day and shows "Update available" in the subtitle if a newer version exists
- Settings screen gains a "Check for update" button that force-fetches from GitHub and notifies with the result
- Update check result cached to `~/.local/state/sshfs-mountctl/update_check.json` to avoid hitting GitHub on every launch

## v1.0.1

- Binary release via GitHub Actions (PyInstaller single-file, no Python required)
- In-app uninstall with option to keep or wipe mount configs — also removes the mount root directory
- Install prompt auto-launches on first run when systemd infra is missing
- Install screen path inputs update the preview list live as you type
- setup.sh prompts for mount root and symlink folder during install (including via `curl | bash`), with descriptions of what each path is used for
- When mount root is outside home, a terminal window opens for the sudo commands — shows exactly what will run, Ctrl+C to cancel and run manually instead; sudo session is revoked immediately after
- Fixed: PyInstaller binary — entry point import error, LD_LIBRARY_PATH interference with systemd/journalctl, watchdog script not found in bundle
- Fixed: `curl | bash` no longer breaks on path prompts in non-interactive shells
- Fixed: settings file preserves unknown keys on save
- Fixed: uninstall cleans up bootstrap git clone at `~/.local/share/sshfs-mountctl`
- Fixed: install status label updates correctly after returning from install screen
- Fixed: app exits automatically after successful uninstall
- Fixed: Back button always shown after install errors

## v1.0.0

Initial release. Built with Python and [Textual](https://github.com/Textualize/textual).
