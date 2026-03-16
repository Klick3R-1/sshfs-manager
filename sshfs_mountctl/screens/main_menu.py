"""MainMenuScreen — top-level navigation and action dispatch."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Static
from textual import work

from ..logging_ import logger
from ..system import (
    conf_for,
    disable_mount_by_name,
    get_mount_status,
    is_installed,
    list_mount_names,
    parse_conf,
    reload_user_daemon,
    systemctl_user,
    unit_for,
)
from .add_mount import AddMountScreen
from .confirm import BulkRemoveConfirmScreen
from .install import InstallScreen
from .log_viewer import LogViewerScreen
from .selector import MountSelectorScreen
from .settings import SettingsScreen


class MenuButton(Static, can_focus=True):
    class Pressed(Message):
        def __init__(self, button: "MenuButton") -> None:
            super().__init__()
            self.button = button

    def __init__(self, label: str, *, id: str) -> None:
        super().__init__(label, id=id, classes="menu-btn")

    def _press(self) -> None:
        self.post_message(MenuButton.Pressed(self))

    def on_click(self) -> None:
        self._press()

    def on_key(self, event) -> None:
        if event.key == "enter":
            self._press()


class MainMenuScreen(Screen):
    BINDINGS = [
        Binding("r", "refresh_mounts", "Refresh"),
        Binding("q", "app.exit",       "Quit"),
    ]

    def compose(self):
        logger.debug("MainMenuScreen.compose")
        yield Header(show_clock=True)
        installed = is_installed()
        status_text = "✓ Installed" if installed else "✗ Not installed"
        with Horizontal(id="main-layout"):
            with Vertical(id="menu-panel"):
                yield Label("Mounts", classes="menu-section-label")
                yield MenuButton("Add",      id="add")
                yield MenuButton("Edit",     id="view")
                yield MenuButton("Clone",    id="clone")
                yield MenuButton("Remove",   id="remove")
                yield MenuButton("Enable",   id="enable")
                yield MenuButton("Disable",  id="disable")
                yield MenuButton("Restart",  id="restart")
                yield Label("General", classes="menu-section-label")
                yield MenuButton("View logs", id="logs")
                yield MenuButton("Install",   id="install")
                yield MenuButton("Settings",  id="settings")
                yield MenuButton("Exit",      id="exit")
                yield Label(status_text, id="install-status")
            with Vertical(id="status-panel"):
                yield DataTable(id="mount-table", cursor_type="none")
        yield Footer()

    def on_mount(self) -> None:
        logger.debug("MainMenuScreen.on_mount")
        installed = is_installed()
        colour = "green" if installed else "yellow"
        self.query_one("#install-status", Label).styles.color = colour
        if not installed:
            self.app.push_screen(InstallScreen())
        self.query_one(DataTable).add_columns(
            "NAME", "ENABLED", "MOUNTED", "SERVICE", "REMOTE"
        )
        self._load_mounts()
        self.set_interval(5, self._load_mounts)

    def on_screen_resume(self) -> None:
        logger.debug("MainMenuScreen.on_screen_resume")
        self._load_mounts()

    def action_refresh_mounts(self) -> None:
        self._load_mounts()

    @work(thread=True)
    def _load_mounts(self) -> None:
        logger.debug("MainMenuScreen._load_mounts")
        rows = []
        for name in list_mount_names():
            try:
                cfg = parse_conf(conf_for(name))
                st  = get_mount_status(name)
                rows.append((name, st.enabled, st.mounted, st.service_state, cfg.remote))
            except Exception as exc:
                logger.debug("  error for %r: %s", name, exc)
                rows.append((name, False, False, "unknown", "?"))

        def update() -> None:
            table = self.query_one(DataTable)
            table.clear()
            for name, enabled, mounted, state, remote in rows:
                en = Text("yes", style="green") if enabled else Text("no",  style="yellow")
                mo = Text("yes", style="green") if mounted else Text("no",  style="yellow")
                st_style = {"active": "green", "failed": "red"}.get(state, "yellow")
                table.add_row(name, en, mo, Text(state, style=st_style), remote)

        self.app.call_from_thread(update)

    # ── Button dispatch ──────────────────────────────────────────────────────

    def on_menu_button_pressed(self, event: MenuButton.Pressed) -> None:
        item_id = event.button.id or ""
        logger.debug("MainMenuScreen.on_menu_button_pressed: %r", item_id)
        self._dispatch(item_id)

    def _dispatch(self, item_id: str) -> None:
        logger.debug("MainMenuScreen._dispatch(%r)", item_id)
        if item_id == "add":
            self.app.push_screen(AddMountScreen())
        elif item_id == "remove":
            self.app.push_screen(
                MountSelectorScreen("Remove mounts", multi=True),
                lambda names: self.app.push_screen(
                    BulkRemoveConfirmScreen(names),
                    self.app.handle_remove,  # type: ignore[attr-defined]
                ) if names else None,
            )
        elif item_id == "enable":
            self.app.push_screen(
                MountSelectorScreen("Enable mounts", multi=True),
                lambda names: self._enable(names) if names else None,
            )
        elif item_id == "disable":
            self.app.push_screen(
                MountSelectorScreen("Disable mounts", multi=True),
                lambda names: self._disable(names) if names else None,
            )
        elif item_id == "restart":
            self.app.push_screen(
                MountSelectorScreen("Restart mounts", multi=True),
                lambda names: self._restart(names) if names else None,
            )
        elif item_id == "clone":
            self.app.push_screen(
                MountSelectorScreen("Clone mountpoint"),
                self._open_clone,
            )
        elif item_id == "view":
            self.app.push_screen(
                MountSelectorScreen("Edit mount config"),
                self._open_edit,
            )
        elif item_id == "logs":
            self.app.push_screen(
                MountSelectorScreen("View logs"),
                lambda name: self.app.push_screen(LogViewerScreen(name)) if name else None,
            )
        elif item_id == "install":
            self.app.push_screen(InstallScreen())
        elif item_id == "settings":
            self.app.push_screen(SettingsScreen())
        elif item_id == "exit":
            self.app.exit()

    def _open_edit(self, name: str | None) -> None:
        if not name:
            return
        logger.debug("MainMenuScreen._open_edit(%r)", name)
        try:
            source = parse_conf(conf_for(name))
            enabled = get_mount_status(name).enabled
        except Exception as exc:
            self.app.notify(f"Could not read config: {exc}", severity="error")
            return
        self.app.push_screen(AddMountScreen(source=source, edit_mode=True, source_enabled=enabled))

    def _open_clone(self, name: str | None) -> None:
        if not name:
            return
        logger.debug("MainMenuScreen._open_clone(%r)", name)
        try:
            source = parse_conf(conf_for(name))
        except Exception as exc:
            self.app.notify(f"Could not read config: {exc}", severity="error")
            return
        self.app.push_screen(AddMountScreen(source=source))

    # ── Workers ──────────────────────────────────────────────────────────────

    @work(thread=True)
    def _enable(self, names: list[str]) -> None:
        logger.debug("MainMenuScreen._enable(%s)", names)
        reload_user_daemon()
        for name in names:
            r = systemctl_user("enable", "--now", unit_for(name))
            msg = (f"Enabled: {name}" if r.returncode == 0
                   else f"Failed to enable {name}: {r.stderr.strip()}")
            sev = "information" if r.returncode == 0 else "error"
            self.app.call_from_thread(self.app.notify, msg, severity=sev)
        self.app.call_from_thread(self._load_mounts)

    @work(thread=True)
    def _disable(self, names: list[str]) -> None:
        logger.debug("MainMenuScreen._disable(%s)", names)
        for name in names:
            disable_mount_by_name(name)
        reload_user_daemon()
        label = ", ".join(names)
        self.app.call_from_thread(
            self.app.notify, f"Disabled: {label}", severity="information"
        )
        self.app.call_from_thread(self._load_mounts)

    @work(thread=True)
    def _restart(self, names: list[str]) -> None:
        logger.debug("MainMenuScreen._restart(%s)", names)
        reload_user_daemon()
        for name in names:
            r = systemctl_user("restart", unit_for(name))
            msg = (f"Restarted: {name}" if r.returncode == 0
                   else f"Restart failed for {name}: {r.stderr.strip()}")
            sev = "information" if r.returncode == 0 else "error"
            self.app.call_from_thread(self.app.notify, msg, severity=sev)
        self.app.call_from_thread(self._load_mounts)
