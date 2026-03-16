"""SettingsScreen — configure LOCAL_LINK_DIR and MOUNT_ROOT."""

from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Switch
from textual import work

from ..logging_ import logger
from ..system import (
    load_settings,
    migrate_link_dir,
    migrate_mount_root,
    save_settings,
)
from ..validators import AbsolutePathValidator


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Cancel")]

    def compose(self):
        logger.debug("SettingsScreen.compose")
        s = load_settings()
        yield Header()
        with VerticalScroll():
            yield Label("Symlink folder  (where ~/Mounts links are created)",
                        classes="field-label")
            yield Input(value=s["LOCAL_LINK_DIR"], id="f_link_dir",
                        validators=[AbsolutePathValidator()])
            yield Label("Default mount root  (parent dir for new mountpoints)",
                        classes="field-label")
            yield Input(value=s["MOUNT_ROOT"], id="f_mount_root",
                        validators=[AbsolutePathValidator()])
            yield Label("Desktop notifications  (global on/off)", classes="field-label")
            yield Switch(value=s["NOTIFICATIONS_ENABLED"] == "1", id="f_notifications")
        with Horizontal(classes="buttons"):
            yield Button("Save", variant="primary", id="btn_save")
            yield Button("Cancel", id="btn_cancel")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        logger.debug("SettingsScreen.on_button_pressed: %r", event.button.id)
        if event.button.id == "btn_cancel":
            self.app.pop_screen()
        elif event.button.id == "btn_save":
            self._save()

    def _save(self) -> None:
        new_link_dir = self.query_one("#f_link_dir", Input).value.strip()
        new_mount_root = self.query_one("#f_mount_root", Input).value.strip()
        if not new_link_dir or not new_mount_root:
            self.app.notify("Both fields are required", severity="error")
            return

        old = load_settings()
        old_link_dir = old["LOCAL_LINK_DIR"]
        old_mount_root = old["MOUNT_ROOT"]

        link_dir_changed = new_link_dir != old_link_dir
        mount_root_changed = new_mount_root != old_mount_root

        logger.debug("SettingsScreen._save: link_dir_changed=%s mount_root_changed=%s",
                     link_dir_changed, mount_root_changed)

        notif = self.query_one("#f_notifications", Switch).value
        save_settings(new_link_dir, new_mount_root, notifications_enabled=notif)

        if not link_dir_changed and not mount_root_changed:
            self.app.notify("Settings saved", severity="information")
            self.app.pop_screen()
            return

        # Pop screen first so the user returns to the main menu while migration runs
        self.app.notify("Settings saved — migrating mounts…", severity="information")
        self.app.pop_screen()

        self._migrate(
            old_link_dir if link_dir_changed else None,
            new_link_dir if link_dir_changed else None,
            old_mount_root if mount_root_changed else None,
            new_mount_root if mount_root_changed else None,
        )

    @work(thread=True)
    def _migrate(
        self,
        old_link_dir: str | None,
        new_link_dir: str | None,
        old_mount_root: str | None,
        new_mount_root: str | None,
    ) -> None:
        logger.debug("SettingsScreen._migrate: link_dir=%s→%s  mount_root=%s→%s",
                     old_link_dir, new_link_dir, old_mount_root, new_mount_root)

        if old_link_dir and new_link_dir:
            try:
                moved = migrate_link_dir(Path(old_link_dir), Path(new_link_dir))
                if moved:
                    msg = f"Moved {len(moved)} symlink(s) to {new_link_dir}"
                else:
                    msg = f"Symlink folder updated (no existing links to move)"
                self.app.call_from_thread(self.app.notify, msg, severity="information")
            except Exception as exc:
                logger.debug("migrate_link_dir error: %s", exc, exc_info=True)
                self.app.call_from_thread(
                    self.app.notify, f"Symlink migration failed: {exc}", severity="error"
                )

        if old_mount_root and new_mount_root:
            try:
                migrated = migrate_mount_root(Path(old_mount_root), Path(new_mount_root))
                if migrated:
                    msg = f"Migrated {len(migrated)} mount(s) to {new_mount_root}"
                else:
                    msg = f"Mount root updated (no existing mounts under old root)"
                self.app.call_from_thread(self.app.notify, msg, severity="information")
            except Exception as exc:
                logger.debug("migrate_mount_root error: %s", exc, exc_info=True)
                self.app.call_from_thread(
                    self.app.notify, f"Mount root migration failed: {exc}", severity="error"
                )
