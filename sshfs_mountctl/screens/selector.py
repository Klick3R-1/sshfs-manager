"""Reusable mount-selector modal used by enable/disable/restart/view/remove."""

from __future__ import annotations

from rich.text import Text
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label
from textual import work

from ..logging_ import logger
from ..system import get_mount_status, list_mount_names

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

    def __init__(self, title: str = "Select mount", multi: bool = False) -> None:
        super().__init__()
        self._title = title
        self._multi = multi
        self._selected: set[str] = set()
        self._row_data: dict[str, tuple[bool, bool, str]] = {}
        logger.debug("MountSelectorScreen: title=%r multi=%s", title, multi)

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
                table.add_row(*_row_cells(name, enabled, mounted, state, False), key=name)

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
