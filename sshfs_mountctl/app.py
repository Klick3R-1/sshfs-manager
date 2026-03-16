"""SshfsMountCtl — the root Textual App."""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual import work

from . import __version__
from .css import APP_CSS
from .logging_ import logger
from .screens import MainMenuScreen
from .system import (
    conf_for,
    mp_for,
    reload_user_daemon,
    remove_local_link,
    systemctl_user,
    unmount,
    unit_for,
)


class SshfsMountCtl(App):
    CSS = APP_CSS
    TITLE = f"SSHFS Mount Control  v{__version__}"
    SUB_TITLE = "by Klick3R"

    def on_mount(self) -> None:
        logger.debug("SshfsMountCtl.on_mount")
        self.push_screen(MainMenuScreen())

    def on_screen_resume(self) -> None:
        logger.debug("SshfsMountCtl.on_screen_resume: screen=%r",
                     type(self.screen).__name__)

    def handle_remove(self, names: list[str] | None) -> None:
        logger.debug("SshfsMountCtl.handle_remove: names=%r", names)
        if names:
            self._do_remove(names)

    @work(thread=True)
    def _do_remove(self, names: list[str]) -> None:
        logger.debug("SshfsMountCtl._do_remove(%r)", names)
        for name in names:
            mp = ""
            try:
                mpfile = mp_for(name)
                if mpfile.exists():
                    mp = mpfile.read_text().strip()
                    logger.debug("  %r mountpoint: %r", name, mp)
            except Exception as exc:
                logger.debug("  could not read .mountpoint for %r: %s", name, exc)

            systemctl_user("stop",    unit_for(name))
            systemctl_user("disable", unit_for(name))
            if mp:
                unmount(mp)
            remove_local_link(name, mp)
            conf_for(name).unlink(missing_ok=True)
            mp_for(name).unlink(missing_ok=True)

            if mp and Path(mp).is_dir():
                logger.debug("  attempting rmdir: %s", mp)
                try:
                    Path(mp).rmdir()
                    logger.debug("  rmdir ok")
                except OSError as exc:
                    logger.debug("  rmdir failed: %s", exc)

        reload_user_daemon()
        label = ", ".join(f"'{n}'" for n in names)
        msg = f"Removed {label}"
        logger.debug("_do_remove done: %r", msg)
        self.call_from_thread(self.notify, msg, severity="information")
