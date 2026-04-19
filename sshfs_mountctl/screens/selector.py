"""Reusable mount-selector modal used by enable/disable/restart/view/remove."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label
from textual import work

from ..logging_ import logger
from ..system import (
    delete_group,
    get_mount_status,
    list_groups,
    list_mounts_by_group,
    list_mount_names,
    rename_group,
)

def _row_cells(
    name: str, enabled: bool, mounted: bool, state: str, selected: bool
) -> tuple:
    en_fg = "green" if enabled else "yellow"
    mo_fg = "green" if mounted else "yellow"
    st_fg = {"active": "green", "failed": "red"}.get(state, "yellow")
    name_text = Text()
    if selected:
        name_text.append("✓ ", style="green bold")
        name_text.append(name, style="green bold")
    else:
        name_text.append(name)
    return (
        name_text,
        Text("yes" if enabled else "no", style=en_fg),
        Text("yes" if mounted else "no", style=mo_fg),
        Text(state,                      style=st_fg),
    )


class MountSelectorScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel",           "Cancel"),
        Binding("q",      "cancel",           "Cancel"),
        Binding("space",  "toggle_selection", "Select", show=False),
    ]

    def __init__(self, title: str = "Select mount", multi: bool = False,
                 pre_selected: set[str] | None = None) -> None:
        super().__init__()
        self._title = title
        self._multi = multi
        self._selected: set[str] = set(pre_selected or [])
        self._row_data: dict[str, tuple[bool, bool, str]] = {}
        logger.debug("MountSelectorScreen: title=%r multi=%s pre_selected=%s",
                     title, multi, self._selected)

    def compose(self):
        hint = "↑↓ navigate · Space toggle · Enter confirm · Esc cancel" if self._multi \
               else "↑↓ navigate · Enter select · Esc cancel"
        with Vertical():
            yield Label(self._title, id="selector-title")
            yield DataTable(id="selector-table", cursor_type="row")
            yield Label(hint, id="selector-hint")

    def on_mount(self) -> None:
        logger.debug("MountSelectorScreen.on_mount")
        self.query_one(DataTable).add_columns("NAME", "ENABLED", "MOUNTED", "SERVICE")
        self._load()

    @work(thread=True)
    def _load(self) -> None:
        logger.debug("MountSelectorScreen._load")
        rows = []
        for name in list_mount_names():
            try:
                st = get_mount_status(name)
                rows.append((name, st.enabled, st.mounted, st.service_state))
            except Exception as exc:
                logger.debug("  status error for %r: %s", name, exc)
                rows.append((name, False, False, "unknown"))

        logger.debug("MountSelectorScreen._load: %d rows", len(rows))

        def update() -> None:
            table = self.query_one(DataTable)
            for name, enabled, mounted, state in rows:
                self._row_data[name] = (enabled, mounted, state)
                table.add_row(*_row_cells(name, enabled, mounted, state,
                                         name in self._selected), key=name)

        self.app.call_from_thread(update)

    def _refresh_row(self, name: str) -> None:
        table = self.query_one(DataTable)
        enabled, mounted, state = self._row_data[name]
        selected = name in self._selected
        cells = _row_cells(name, enabled, mounted, state, selected)
        col_keys = list(table.columns.keys())
        for col_key, value in zip(col_keys, cells):
            table.update_cell(name, col_key, value)

    def action_toggle_selection(self) -> None:
        if not self._multi:
            return
        table = self.query_one(DataTable)
        try:
            row_key = list(table.rows.keys())[table.cursor_row]
        except IndexError:
            return
        name = str(row_key.value)
        if name in self._selected:
            self._selected.discard(name)
        else:
            self._selected.add(name)
        self._refresh_row(name)
        logger.debug("MountSelectorScreen: toggled %r → selected=%s", name, self._selected)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        name = str(event.row_key.value)
        if self._multi:
            names = list(self._selected) or [name]
            logger.debug("MountSelectorScreen: confirmed multi=%s", names)
            self.dismiss(names)
        else:
            logger.debug("MountSelectorScreen: selected %r", name)
            self.dismiss(name)

    def action_cancel(self) -> None:
        logger.debug("MountSelectorScreen: cancelled")
        self.dismiss(None)


class GroupSelectorScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q",      "cancel", "Cancel"),
    ]

    def __init__(self, title: str = "Select group") -> None:
        super().__init__()
        self._title = title
        logger.debug("GroupSelectorScreen: title=%r", title)

    def compose(self):
        with Vertical():
            yield Label(self._title, id="selector-title")
            yield DataTable(id="selector-table", cursor_type="row")
            yield Label("↑↓ navigate · Enter select · Esc cancel", id="selector-hint")

    def on_mount(self) -> None:
        logger.debug("GroupSelectorScreen.on_mount")
        table = self.query_one(DataTable)
        table.add_column("GROUP")
        groups = list_groups()
        if not groups:
            self.app.notify("No groups configured", severity="warning")
            self.dismiss(None)
            return
        for g in groups:
            table.add_row(g, key=g)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        group = str(event.row_key.value)
        logger.debug("GroupSelectorScreen: selected %r", group)
        self.dismiss(group)

    def action_cancel(self) -> None:
        logger.debug("GroupSelectorScreen: cancelled")
        self.dismiss(None)


class GroupManagerScreen(ModalScreen):
    """List all groups with options to add, rename, or delete."""

    BINDINGS = [
        Binding("escape", "cancel", "Close"),
        Binding("q",      "cancel", "Close"),
    ]

    def compose(self):
        with Vertical():
            yield Label("Manage groups", id="selector-title")
            yield DataTable(id="selector-table", cursor_type="row")
            with Horizontal(classes="buttons"):
                yield Button("New",    variant="primary", id="grp_new")
                yield Button("Rename", variant="default", id="grp_rename")
                yield Button("Delete", variant="error",   id="grp_delete")
                yield Button("Close",  variant="default", id="grp_close")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("GROUP", "MOUNTS")
        self._reload()

    def _reload(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        for g in list_groups():
            count = len(list_mounts_by_group(g))
            table.add_row(g, str(count), key=g)

    def _selected_group(self) -> str | None:
        table = self.query_one(DataTable)
        try:
            return str(list(table.rows.keys())[table.cursor_row].value)
        except (IndexError, AttributeError):
            return None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "grp_close":
            self.dismiss(None)
        elif event.button.id == "grp_new":
            self._do_new()
        elif event.button.id == "grp_rename":
            group = self._selected_group()
            if group:
                self._do_rename(group)
        elif event.button.id == "grp_delete":
            group = self._selected_group()
            if group:
                self._do_delete(group)

    def _do_new(self) -> None:
        from .confirm import TextInputScreen
        from ..system import set_mount_group
        def _on_name(name: str | None) -> None:
            if not name:
                return
            if name in list_groups():
                self.app.notify(f"Group '{name}' already exists", severity="warning")
                return
            def _on_members(selected: list[str] | None) -> None:
                if not selected:
                    self.app.notify("No mounts selected — group not created", severity="warning")
                    return
                for mount_name in selected:
                    set_mount_group(mount_name, name)
                self.call_after_refresh(self._reload)
                self.app.notify(f"Created group '{name}' with {len(selected)} mount(s)",
                                severity="information")
            self.app.push_screen(
                MountSelectorScreen(f"Assign mounts to '{name}'", multi=True), _on_members
            )
        self.app.push_screen(TextInputScreen("New group name", placeholder="e.g. work, media"), _on_name)

    def _do_rename(self, group: str) -> None:
        from .confirm import TextInputScreen
        def _on_name(new_name: str | None) -> None:
            if not new_name or new_name == group:
                return
            rename_group(group, new_name)
            self.call_after_refresh(self._reload)
            self.app.notify(f"Renamed '{group}' → '{new_name}'", severity="information")
        self.app.push_screen(
            TextInputScreen("Rename group", placeholder="new name", initial=group), _on_name
        )

    def _do_delete(self, group: str) -> None:
        from .confirm import TextInputScreen
        count = len(list_mounts_by_group(group))
        def _on_confirm(value: str | None) -> None:
            if value and value.lower() in ("yes", "y"):
                delete_group(group)
                self.call_after_refresh(self._reload)
                self.app.notify(f"Deleted group '{group}'", severity="information")
        self.app.push_screen(
            TextInputScreen(
                f"Delete group '{group}'? ({count} mount{'s' if count != 1 else ''})\nType 'yes' to confirm",
                placeholder="yes",
            ), _on_confirm
        )

    def action_cancel(self) -> None:
        self.dismiss(None)
