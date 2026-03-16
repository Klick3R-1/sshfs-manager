"""RemotePathBrowserScreen — navigate a remote filesystem over SSH."""

from __future__ import annotations

import posixpath
import shlex
import subprocess

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Label
from textual import work

from ..logging_ import logger
from ..system import _clean_env


class RemotePathBrowserScreen(ModalScreen):
    """SSH into host and let the user browse directories. Dismisses with the
    chosen absolute path, or None if cancelled."""

    BINDINGS = [
        Binding("escape",    "cancel",  "Cancel"),
        Binding("backspace", "go_up",   "Up"),
        Binding("left",      "go_up",   "Up"),
        Binding("s",         "select",  "Select"),
    ]

    def __init__(self, ssh_target: str, initial_path: str = "~") -> None:
        super().__init__()
        self._target = ssh_target      # may be "user@host" or just "host"
        self._path   = initial_path
        logger.debug("RemotePathBrowserScreen: target=%r initial=%r", ssh_target, initial_path)

    def compose(self):
        with Vertical():
            yield Label("", id="browser-path")
            yield Label("Connecting…", id="browser-status")
            yield DataTable(id="browser-table", cursor_type="row")
            with Horizontal(classes="buttons"):
                yield Button("Select this directory", variant="primary", id="btn_select")
                yield Button("Cancel", id="btn_cancel")

    def on_mount(self) -> None:
        self.query_one(DataTable).add_column("Directory", key="name")
        self._load(self._path)

    # ── SSH worker ──────────────────────────────────────────────────────────────

    @work(thread=True)
    def _load(self, path: str) -> None:
        logger.debug("RemotePathBrowserScreen._load: path=%r", path)
        # Use bare `cd` (no args) to reach home — works on all POSIX shells
        # regardless of whether $HOME is set in the remote environment.
        # For any other path, shlex.quote it.
        is_home = path.strip() in ("~", "$HOME", "")
        if is_home:
            cd_cmd = "cd"
        else:
            cd_cmd = f"cd {shlex.quote(path)}"
        script = f"{cd_cmd} && pwd && ls -1ap ."
        cmd = [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            "-o", "StrictHostKeyChecking=accept-new",
            self._target,
            script,
        ]
        logger.debug("RemotePathBrowserScreen._load: cmd=%r", cmd)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=_clean_env())
        except subprocess.TimeoutExpired:
            self.app.call_from_thread(self._show_error, "SSH timed out")
            return
        logger.debug("RemotePathBrowserScreen._load: rc=%d stdout=%r stderr=%r",
                     r.returncode, r.stdout[:200], r.stderr[:200])

        if r.returncode != 0:
            self.app.call_from_thread(
                self._show_error, r.stderr.strip() or f"rc={r.returncode}"
            )
            return

        lines = r.stdout.splitlines()
        if not lines:
            self.app.call_from_thread(self._show_error, "Empty response from host")
            return

        resolved = lines[0].strip()
        # Keep only directory entries, drop ./ and ../
        dirs = [
            l.rstrip("/") for l in lines[1:]
            if l.endswith("/") and l not in ("./", "../")
        ]
        logger.debug("  resolved=%r  dirs=%d", resolved, len(dirs))
        self.app.call_from_thread(self._update, resolved, dirs)

    # ── UI updates (main thread) ────────────────────────────────────────────────

    def _show_error(self, msg: str) -> None:
        self.query_one("#browser-status", Label).update(f"[red]{msg}[/red]")

    def _update(self, resolved: str, dirs: list[str]) -> None:
        self._path = resolved
        self.query_one("#browser-path", Label).update(
            f"[bold]{self._target}[/bold]:{resolved}"
        )
        table = self.query_one(DataTable)
        table.clear()
        if resolved != "/":
            table.add_row("..", key="..")
        for d in dirs:
            table.add_row(d, key=d)
        n = len(dirs)
        self.query_one("#browser-status", Label).update(
            f"{n} director{'y' if n == 1 else 'ies'} · "
            "↑↓ navigate · Enter/→ open · Backspace/← go up · S select"
        )

    # ── Navigation ──────────────────────────────────────────────────────────────

    def _navigate_to(self, path: str) -> None:
        self.query_one(DataTable).clear()
        self.query_one("#browser-status", Label).update("Loading…")
        self._load(path)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = str(event.row_key.value)
        if key == "..":
            self.action_go_up()
        else:
            self._navigate_to(posixpath.join(self._path, key))

    def action_go_up(self) -> None:
        parent = posixpath.dirname(self._path.rstrip("/")) or "/"
        logger.debug("RemotePathBrowserScreen: go up → %r", parent)
        self._navigate_to(parent)

    # ── Confirm / cancel ────────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_select":
            self.action_select()
        elif event.button.id == "btn_cancel":
            self.action_cancel()

    def action_select(self) -> None:
        logger.debug("RemotePathBrowserScreen: selected %r", self._path)
        self.dismiss(self._path)

    def action_cancel(self) -> None:
        logger.debug("RemotePathBrowserScreen: cancelled")
        self.dismiss(None)
