"""InstallScreen — create/update all required files and directories."""

from __future__ import annotations

import os
import pwd
import shutil
import subprocess

from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Log
from textual import work

from ..constants import (
    HOME,
    MOUNTS_DIR,
    SYSTEMD_DIR,
    UNIT_TEMPLATE,
    UNIT_TEMPLATE_CONTENT,
    WATCHDOG_DST,
    WATCHDOG_SRC,
)
from ..logging_ import logger
from ..system import (
    _clean_env,
    disable_mount_by_name,
    ensure_bin_in_path,
    get_local_link_dir,
    get_mount_root,
    list_mount_names,
    load_settings,
    reload_user_daemon,
    save_settings,
)
from .confirm import UninstallConfirmScreen
from ..validators import AbsolutePathValidator

_TERMINAL_PREFIXES = [
    ["xterm", "-e"],
    ["alacritty", "-e"],
    ["kitty"],
    ["foot"],
    ["wezterm", "start", "--"],
    ["gnome-terminal", "--wait", "--"],
    ["konsole", "-e"],
    ["xfce4-terminal", "--hold", "-e"],
]


def _sudo_in_terminal(shell_cmd: str) -> None:
    """Spawn the first available terminal emulator to run shell_cmd interactively."""
    for prefix in _TERMINAL_PREFIXES:
        if shutil.which(prefix[0]):
            subprocess.run(prefix + ["bash", "-c", shell_cmd], env=_clean_env())
            return


class InstallScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Cancel")]

    def compose(self):
        logger.debug("InstallScreen.compose")
        s = load_settings()
        yield Header()
        yield Label("The following will be created or updated:", id="install-header")
        yield Label("Symlink folder", classes="field-label install-path-label")
        yield Input(value=s["LOCAL_LINK_DIR"], id="f_link_dir",
                    validators=[AbsolutePathValidator()])
        yield Label("Mount root  (may require sudo if outside home)", classes="field-label install-path-label")
        yield Input(value=s["MOUNT_ROOT"], id="f_mount_root",
                    validators=[AbsolutePathValidator()])
        yield Log(id="install-log", auto_scroll=True)
        with Horizontal(classes="buttons", id="install-buttons"):
            yield Button("Proceed",   variant="primary", id="btn_proceed")
            yield Button("Uninstall", variant="error",   id="btn_uninstall")
            yield Button("Cancel",    id="btn_cancel")
        with Horizontal(classes="buttons", id="back-buttons"):
            yield Button("Back to menu", variant="primary", id="btn_back")
        yield Footer()

    def on_mount(self) -> None:
        logger.debug("InstallScreen.on_mount")
        self.query_one("#back-buttons").display = False
        log = self.query_one(Log)
        link_dir = get_local_link_dir()
        mount_root = get_mount_root()
        for path in [MOUNTS_DIR, SYSTEMD_DIR, HOME / ".bin", link_dir,
                     UNIT_TEMPLATE, WATCHDOG_DST]:
            log.write_line(f"  {path}")
        needs_sudo = not str(mount_root).startswith(str(HOME))
        sudo_note = "  (may require sudo)" if needs_sudo else ""
        log.write_line(f"  {mount_root}{sudo_note}")

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id not in ("f_link_dir", "f_mount_root"):
            return
        link_dir = self.query_one("#f_link_dir", Input).value.strip() or str(get_local_link_dir())
        mount_root = self.query_one("#f_mount_root", Input).value.strip() or str(get_mount_root())
        log = self.query_one(Log)
        log.clear()
        for path in [MOUNTS_DIR, SYSTEMD_DIR, HOME / ".bin", link_dir,
                     UNIT_TEMPLATE, WATCHDOG_DST]:
            log.write_line(f"  {path}")
        needs_sudo = not mount_root.startswith(str(HOME))
        sudo_note = "  (may require sudo)" if needs_sudo else ""
        log.write_line(f"  {mount_root}{sudo_note}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        logger.debug("InstallScreen.on_button_pressed: %r", event.button.id)
        if event.button.id == "btn_cancel":
            self.app.pop_screen()
        elif event.button.id == "btn_proceed":
            link_dir = self.query_one("#f_link_dir", Input).value.strip()
            mount_root = self.query_one("#f_mount_root", Input).value.strip()
            if not link_dir or not mount_root:
                self.app.notify("Both path fields are required", severity="error")
                return
            save_settings(link_dir, mount_root)
            self.query_one("#install-buttons").display = False
            self._run_install()
        elif event.button.id == "btn_uninstall":
            self.app.push_screen(UninstallConfirmScreen(), self._on_uninstall_confirm)
        elif event.button.id == "btn_back":
            self.app.pop_screen()

    @work(thread=True)
    def _run_install(self) -> None:
        logger.debug("InstallScreen._run_install: starting")

        def log(msg: str) -> None:
            logger.debug("install: %s", msg)
            self.app.call_from_thread(self.query_one(Log).write_line, msg)

        try:
            if not WATCHDOG_SRC.exists():
                log(f"ERROR: source watchdog not found: {WATCHDOG_SRC}")
                return

            link_dir = get_local_link_dir()
            mount_root = get_mount_root()

            for d in [MOUNTS_DIR, SYSTEMD_DIR, HOME / ".bin", link_dir]:
                d.mkdir(parents=True, exist_ok=True)
                logger.debug("  ensured: %s", d)

            for f in ensure_bin_in_path():
                log(f"  added ~/.bin to PATH in: {f}")

            UNIT_TEMPLATE.write_text(UNIT_TEMPLATE_CONTENT)
            log(f"  wrote unit template: {UNIT_TEMPLATE}")

            shutil.copy2(WATCHDOG_SRC, WATCHDOG_DST)
            WATCHDOG_DST.chmod(0o755)
            log(f"  installed watchdog: {WATCHDOG_DST}")

            if not mount_root.exists():
                # If inside home dir, no sudo needed
                if str(mount_root).startswith(str(HOME)):
                    mount_root.mkdir(parents=True, exist_ok=True)
                    log(f"  created {mount_root}")
                else:
                    user = pwd.getpwuid(os.getuid()).pw_name
                    shell_cmd = (
                        f"echo 'Creating {mount_root} — sudo password required' && "
                        f"sudo mkdir -p {mount_root} && "
                        f"sudo chown {user}:{user} {mount_root} && "
                        f"sudo chmod 755 {mount_root} && "
                        f"sudo -k && "
                        f"echo 'Done!' || echo 'Something went wrong.'; "
                        f"read -rp 'Press Enter to close…'"
                    )
                    log(f"  Opening terminal to create {mount_root}…")
                    _sudo_in_terminal(shell_cmd)
                    if not mount_root.exists():
                        log(f"  ERROR: {mount_root} was not created")
                        log(f"  Run manually:  sudo mkdir -p {mount_root} && sudo chown $(id -un) {mount_root}")
                        log(f"  Then re-open Install to complete setup.")
                        return
                    log(f"  created {mount_root}")

            reload_user_daemon()
            log("  systemd user daemon reloaded")
            log("")
            log("Install complete.")
            logger.debug("install: done")

        except Exception as exc:
            logger.debug("install: exception: %s", exc, exc_info=True)
            log(f"ERROR: {exc}")

        finally:
            self.app.call_from_thread(
                lambda: setattr(self.query_one("#back-buttons"), "display", True)
            )

    def _on_uninstall_confirm(self, result: str | None) -> None:
        if result is None:
            return
        self.query_one("#install-buttons").display = False
        self._run_uninstall(result == "wipe")

    @work(thread=True)
    def _run_uninstall(self, wipe_configs: bool) -> None:
        logger.debug("InstallScreen._run_uninstall: wipe_configs=%s", wipe_configs)

        def log(msg: str) -> None:
            logger.debug("uninstall: %s", msg)
            self.app.call_from_thread(self.query_one(Log).write_line, msg)

        try:
            log("Stopping and disabling all mounts…")
            for name in list_mount_names():
                try:
                    disable_mount_by_name(name)
                    log(f"  stopped: {name}")
                except Exception as exc:
                    log(f"  warning: could not stop {name}: {exc}")

            reload_user_daemon()

            for path in [UNIT_TEMPLATE, WATCHDOG_DST, HOME / ".bin" / "sshfs-mountctl"]:
                if path.exists():
                    path.unlink()
                    log(f"  removed: {path}")

            lib_dir = HOME / ".local" / "lib" / "sshfs-mountctl"
            if lib_dir.exists():
                shutil.rmtree(lib_dir)
                log(f"  removed: {lib_dir}")

            share_dir = HOME / ".local" / "share" / "sshfs-mountctl"
            if share_dir.exists():
                shutil.rmtree(share_dir)
                log(f"  removed: {share_dir}")

            if wipe_configs:
                if MOUNTS_DIR.exists():
                    shutil.rmtree(MOUNTS_DIR)
                    log(f"  removed: {MOUNTS_DIR}")

            mount_root = get_mount_root()
            if mount_root.exists():
                if str(mount_root).startswith(str(HOME)):
                    try:
                        mount_root.rmdir()
                        log(f"  removed: {mount_root}")
                    except OSError:
                        log(f"  skipped: {mount_root}  (not empty)")
                else:
                    shell_cmd = (
                        f"echo 'Removing {mount_root} — sudo password required' && "
                        f"sudo rmdir {mount_root} && "
                        f"sudo -k && "
                        f"echo 'Done!' || echo 'Could not remove {mount_root} (may not be empty).'; "
                        f"read -rp 'Press Enter to close…'"
                    )
                    log(f"  Opening terminal to remove {mount_root}…")
                    _sudo_in_terminal(shell_cmd)
                    if mount_root.exists():
                        log(f"  skipped: {mount_root}  (not empty or sudo cancelled)")
                    else:
                        log(f"  removed: {mount_root}")

            log("")
            log("Uninstall complete. Closing…")
            if not wipe_configs:
                log("Mount configs kept at ~/.config/sshfs-mounts/")
            import time; time.sleep(2)
            self.app.call_from_thread(self.app.exit)
            return

        except Exception as exc:
            logger.debug("uninstall: exception: %s", exc, exc_info=True)
            log(f"ERROR: {exc}")

        self.app.call_from_thread(
            lambda: setattr(self.query_one("#back-buttons"), "display", True)
        )
