"""LogViewerScreen — stream journalctl output for a single SSHFS mount."""

from __future__ import annotations

import subprocess
import threading

from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Log

from ..logging_ import logger
from ..system import unit_for, _clean_env


class LogViewerScreen(Screen):
    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("q",      "app.pop_screen", "Back"),
        Binding("f",      "toggle_follow",  "Follow"),
        Binding("r",      "reload",         "Reload"),
    ]

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name   = name
        self._unit   = unit_for(name)
        self._follow = False
        self._proc: subprocess.Popen | None = None
        self._stop   = threading.Event()
        logger.debug("LogViewerScreen.__init__: name=%r unit=%r", name, self._unit)

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self):
        yield Header()
        yield Label(f"Logs: {self._unit}", id="log-title")
        yield Log(id="log-widget", highlight=True)
        with Horizontal(classes="buttons"):
            yield Button("Follow", id="btn_follow")
            yield Button("Reload", id="btn_reload")
            yield Button("Back",   id="btn_back")
        yield Footer()

    def on_mount(self) -> None:
        logger.debug("LogViewerScreen.on_mount")
        self._load_static()

    def on_unmount(self) -> None:
        logger.debug("LogViewerScreen.on_unmount: stopping follow thread")
        self._stop_follow()

    # ── Button handling ──────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        logger.debug("LogViewerScreen.on_button_pressed: %r", event.button.id)
        if event.button.id == "btn_back":
            self.app.pop_screen()
        elif event.button.id == "btn_reload":
            self.action_reload()
        elif event.button.id == "btn_follow":
            self.action_toggle_follow()

    # ── Actions ──────────────────────────────────────────────────────────────

    def action_reload(self) -> None:
        logger.debug("LogViewerScreen.action_reload")
        self._stop_follow()
        self._follow = False
        self._update_follow_button()
        self._load_static()

    def action_toggle_follow(self) -> None:
        self._follow = not self._follow
        logger.debug("LogViewerScreen.action_toggle_follow: follow=%s", self._follow)
        self._update_follow_button()
        if self._follow:
            self._start_follow()
        else:
            self._stop_follow()

    def _update_follow_button(self) -> None:
        btn = self.query_one("#btn_follow", Button)
        btn.variant = "primary" if self._follow else "default"
        btn.label   = "Following…" if self._follow else "Follow"

    # ── Static load (last N lines) ───────────────────────────────────────────

    def _load_static(self) -> None:
        log_widget = self.query_one("#log-widget", Log)
        log_widget.clear()
        log_widget.write_line("Loading…")
        threading.Thread(target=self._fetch_static, daemon=True).start()

    def _fetch_static(self) -> None:
        cmd = [
            "journalctl", "--user",
            "-u", self._unit,
            "-n", "300",
            "--no-pager",
            "--output=short-iso",
        ]
        logger.debug("LogViewerScreen._fetch_static: cmd=%r", cmd)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=_clean_env())
            lines = r.stdout.splitlines() or ["(no log entries)"]
            logger.debug("LogViewerScreen._fetch_static: %d lines, rc=%d", len(lines), r.returncode)
        except Exception as exc:
            logger.debug("LogViewerScreen._fetch_static error: %s", exc)
            lines = [f"Error: {exc}"]
        self.app.call_from_thread(self._display_static, lines)

    def _display_static(self, lines: list[str]) -> None:
        log_widget = self.query_one("#log-widget", Log)
        log_widget.clear()
        for line in lines:
            log_widget.write_line(line)

    # ── Follow mode (streaming) ───────────────────────────────────────────────

    def _start_follow(self) -> None:
        self._stop_follow()          # ensure any previous thread is gone
        self._stop.clear()
        log_widget = self.query_one("#log-widget", Log)
        log_widget.clear()
        log_widget.write_line("Following logs… (press F to stop)")
        threading.Thread(target=self._stream_follow, daemon=True).start()

    def _stream_follow(self) -> None:
        cmd = [
            "journalctl", "--user",
            "-u", self._unit,
            "-f", "-n", "50",
            "--no-pager",
            "--output=short-iso",
        ]
        logger.debug("LogViewerScreen._stream_follow: cmd=%r", cmd)
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, env=_clean_env(),
            )
            for line in self._proc.stdout:  # type: ignore[union-attr]
                if self._stop.is_set():
                    break
                self.app.call_from_thread(
                    self.query_one("#log-widget", Log).write_line,
                    line.rstrip(),
                )
        except Exception as exc:
            logger.debug("LogViewerScreen._stream_follow error: %s", exc)
            self.app.call_from_thread(
                self.query_one("#log-widget", Log).write_line,
                f"[red]Stream error: {exc}[/red]",
            )
        finally:
            self._proc = None

    def _stop_follow(self) -> None:
        self._stop.set()
        if self._proc:
            logger.debug("LogViewerScreen._stop_follow: terminating pid=%d", self._proc.pid)
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None
