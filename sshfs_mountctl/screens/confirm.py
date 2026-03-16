"""Confirm modal dialogs for remove operations."""

from __future__ import annotations

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Rule

from ..logging_ import logger
from ..system import conf_for, mp_for, unit_for


class RemoveConfirmScreen(ModalScreen):
    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name
        logger.debug("RemoveConfirmScreen: name=%r", name)

    def compose(self):
        unit = unit_for(self._name)
        mp = ""
        try:
            mpfile = mp_for(self._name)
            if mpfile.exists():
                mp = mpfile.read_text().strip()
                logger.debug("  mountpoint: %r", mp)
        except Exception as exc:
            logger.debug("  could not read .mountpoint: %s", exc)

        with Vertical():
            yield Label(f"[bold]Remove mount '{self._name}'?[/bold]")
            yield Rule()
            yield Label(f"  Stop + disable:  {unit}")
            if mp:
                yield Label(f"  Unmount:         {mp}  (if mounted)")
            yield Label(f"  Delete:          {conf_for(self._name)}")
            yield Label(f"  Delete:          {mp_for(self._name)}")
            if mp:
                yield Label(f"  Remove dir:      {mp}  (if empty)")
            yield Rule()
            with Horizontal(classes="buttons"):
                yield Button("Remove", variant="error",   id="confirm")
                yield Button("Cancel", variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            logger.debug("RemoveConfirmScreen: confirmed removal of %r", self._name)
            self.dismiss(self._name)
        else:
            logger.debug("RemoveConfirmScreen: cancelled")
            self.dismiss(None)


class BulkRemoveConfirmScreen(ModalScreen):
    def __init__(self, names: list[str]) -> None:
        super().__init__()
        self._names = names
        logger.debug("BulkRemoveConfirmScreen: names=%r", names)

    def compose(self):
        n = len(self._names)
        with Vertical():
            yield Label(f"[bold]Remove {n} mount{'s' if n != 1 else ''}?[/bold]")
            yield Rule()
            for name in self._names:
                yield Label(f"  {name}")
            yield Rule()
            yield Label("Each will be stopped, disabled, unmounted, and deleted.",
                        classes="field-label")
            with Horizontal(classes="buttons"):
                yield Button("Remove all", variant="error",   id="confirm")
                yield Button("Cancel",     variant="default", id="cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            logger.debug("BulkRemoveConfirmScreen: confirmed %r", self._names)
            self.dismiss(self._names)
        else:
            logger.debug("BulkRemoveConfirmScreen: cancelled")
            self.dismiss(None)
