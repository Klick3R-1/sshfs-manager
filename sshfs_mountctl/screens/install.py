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
    ensure_bin_in_path,
    get_local_link_dir,
    get_mount_root,
    load_settings,
    reload_user_daemon,
    save_settings,
)
from ..validators import AbsolutePathValidator


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
            yield Button("Proceed", variant="primary", id="btn_proceed")
            yield Button("Cancel",  id="btn_cancel")
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
                    cmd = ["sudo", "mkdir", "-p", str(mount_root)]
                    logger.debug("  run: %s", " ".join(cmd))
                    r = subprocess.run(cmd, capture_output=True, text=True, env=_clean_env())
                    logger.debug("  → rc=%d stderr=%r", r.returncode, r.stderr.strip())
                    if r.returncode != 0:
                        log(f"  ERROR creating {mount_root}: {r.stderr.strip()}")
                        return

                    user = pwd.getpwuid(os.getuid()).pw_name
                    for cmd in [
                        ["sudo", "chown", f"{user}:{user}", str(mount_root)],
                        ["sudo", "chmod", "755", str(mount_root)],
                    ]:
                        logger.debug("  run: %s", " ".join(cmd))
                        subprocess.run(cmd, capture_output=True, env=_clean_env())
                    log(f"  {mount_root} owned by {user}")

            reload_user_daemon()
            log("  systemd user daemon reloaded")
            log("")
            log("Install complete.")
            logger.debug("install: done")

        except Exception as exc:
            logger.debug("install: exception: %s", exc, exc_info=True)
            log(f"ERROR: {exc}")

        self.app.call_from_thread(
            lambda: setattr(self.query_one("#back-buttons"), "display", True)
        )
