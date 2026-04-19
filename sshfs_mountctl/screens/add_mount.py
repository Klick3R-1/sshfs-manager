"""AddMountScreen — form for creating a new SSHFS mount."""

from __future__ import annotations

from pathlib import Path

from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.suggester import SuggestFromList
from textual.widgets import Button, Footer, Header, Input, Label, Rule, Switch
from textual import work

from ..logging_ import logger
from ..models import MountConfig
from ..system import (
    conf_for,
    ensure_local_link,
    get_mount_root,
    list_groups,
    mp_for,
    parse_remote_host,
    reload_user_daemon,
    ssh_config_hostname,
    ssh_config_hosts,
    systemctl_user,
    test_ssh_connection,
    unit_for,
    write_conf,
    unmount,
)
from ..validators import AbsolutePathValidator, MountNameValidator, PositiveIntValidator
from .remote_browser import RemotePathBrowserScreen


class AddMountScreen(Screen):
    BINDINGS = [Binding("escape", "app.pop_screen", "Cancel")]

    def __init__(self, source: MountConfig | None = None, edit_mode: bool = False,
                 source_enabled: bool = True) -> None:
        super().__init__()
        self._source = source
        self._edit_mode = edit_mode
        self._source_enabled = source_enabled
        self._mp_touched = edit_mode  # don't auto-fill mountpoint when editing
        self._hc_touched = source is not None
        logger.debug("AddMountScreen.__init__: clone=%s edit=%s enabled=%s",
                     source.name if source else None, edit_mode, source_enabled)

    def compose(self):
        s = self._source
        logger.debug("AddMountScreen.compose: clone=%s", s.name if s else None)
        hosts = ssh_config_hosts()
        host_suggester = SuggestFromList(hosts, case_sensitive=False) if hosts else None
        groups = list_groups()
        group_suggester = SuggestFromList(groups, case_sensitive=False) if groups else None

        yield Header()
        with VerticalScroll():
            if s and not self._edit_mode:
                yield Label(f"Cloning from:  {s.name}", classes="clone-banner")

            yield Label("Mount name", classes="field-label")
            yield Input(value=s.name if (s and self._edit_mode) else "",
                        placeholder="e.g. myserver, media, backup",
                        id="f_name", validators=[MountNameValidator()],
                        disabled=self._edit_mode)

            yield Label("Remote  (user@host:/path)", classes="field-label")
            yield Input(value=s.remote if s else "",
                        placeholder="e.g. myserver:/srv/media",
                        id="f_remote", suggester=host_suggester)
            with Horizontal(classes="inline-buttons"):
                yield Button("Test connection", id="btn_test_ssh", variant="default")
                yield Button("Browse remote…", id="btn_browse_remote", variant="default")
            yield Label("", id="ssh-test-result", classes="ssh-test-result")

            yield Label("Local mountpoint", classes="field-label")
            yield Input(value=s.mountpoint if (s and self._edit_mode) else "",
                        placeholder=f"{get_mount_root()}/<name>",
                        id="f_mountpoint", validators=[AbsolutePathValidator()])

            yield Label("Retry interval (seconds)", classes="field-label")
            yield Input(value=str(s.retry_secs) if s else "120",
                        id="f_retry", validators=[PositiveIntValidator(5)])

            yield Label("Connect timeout (seconds)", classes="field-label")
            yield Input(value=str(s.connect_timeout) if s else "10",
                        id="f_timeout", validators=[PositiveIntValidator(1)])

            yield Label("SSHFS options", classes="field-label")
            yield Input(
                value=s.sshfs_opts if s else
                    "reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no",
                id="f_opts",
            )

            yield Rule()
            yield Label("Offline auto-unmount health check", classes="field-label")
            yield Switch(value=s.healthcheck_enabled if s else True, id="f_hc_enabled")

            with Vertical(id="hc_group", classes="healthcheck-group"):
                yield Label("Health check host  (blank = auto from Remote)",
                            classes="field-label")
                yield Input(value=s.healthcheck_host if s else "",
                            placeholder="auto-detected", id="f_hc_host",
                            suggester=host_suggester)

                yield Label("Check method", classes="field-label")
                yield Switch(value=(s.healthcheck_mode == "tcp") if s else False,
                             id="f_hc_tcp")
                yield Label("TCP  (off = ping  ·  on = TCP port check)",
                            classes="field-label")

                with Vertical(id="f_hc_port_group"):
                    yield Label("TCP port", classes="field-label")
                    yield Input(value=str(s.healthcheck_port) if s else "22",
                                id="f_hc_port", validators=[PositiveIntValidator(1)])

                yield Label("Consecutive failures before unmount", classes="field-label")
                yield Input(value=str(s.healthcheck_fails) if s else "3",
                            id="f_hc_fails", validators=[PositiveIntValidator(1)])

                yield Label("Ping / connect timeout (seconds)", classes="field-label")
                yield Input(value=str(s.ping_timeout) if s else "2",
                            id="f_hc_ping", validators=[PositiveIntValidator(1)])

            yield Rule()
            yield Label("Desktop notifications", classes="field-label")
            yield Switch(value=s.notifications_enabled if s else False, id="f_notifications")

            yield Rule()
            yield Label("Group  (optional)", classes="field-label")
            yield Input(value=s.group if s else "",
                        placeholder="e.g. work, media, home",
                        id="f_group", suggester=group_suggester)

            yield Rule()
            yield Label(
                "Restart to apply changes" if self._edit_mode else "Enable and start after creation",
                classes="field-label",
            )
            yield Switch(value=self._source_enabled if self._edit_mode else True, id="f_enable_after")

        with Horizontal(classes="buttons"):
            yield Button("Save" if self._edit_mode else "Create", variant="primary", id="btn_create")
            yield Button("Cancel", id="btn_cancel")
        yield Footer()

    def on_mount(self) -> None:
        logger.debug("AddMountScreen.on_mount")
        if self._edit_mode:
            self.query_one("#f_remote", Input).focus()
        else:
            self.query_one("#f_name", Input).focus()
        # Hide healthcheck group if healthcheck is disabled
        hc_on = self.query_one("#f_hc_enabled", Switch).value
        self.query_one("#hc_group").display = hc_on
        # TCP port field hidden unless TCP mode is on
        tcp_on = self._source.healthcheck_mode == "tcp" if self._source else False
        self.query_one("#f_hc_port_group").display = tcp_on

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "f_hc_enabled":
            logger.debug("AddMountScreen: healthcheck switch → %s", event.value)
            self.query_one("#hc_group").display = event.value
        elif event.switch.id == "f_hc_tcp":
            logger.debug("AddMountScreen: tcp mode switch → %s", event.value)
            self.query_one("#f_hc_port_group").display = event.value

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "f_name" and not self._mp_touched:
            new_mp = str(get_mount_root() / event.value) if event.value else ""
            logger.debug("AddMountScreen: name changed → auto-fill mountpoint=%r", new_mp)
            self.query_one("#f_mountpoint", Input).value = new_mp
        elif event.input.id == "f_remote" and not self._hc_touched:
            raw_host = parse_remote_host(event.value) if event.value else ""
            resolved = ssh_config_hostname(raw_host) if raw_host else ""
            logger.debug("AddMountScreen: remote changed → auto-fill hc_host=%r", resolved)
            self.query_one("#f_hc_host", Input).value = resolved

    def on_input_focus(self, event: Input.Focus) -> None:
        if event.input.id == "f_mountpoint":
            logger.debug("AddMountScreen: mountpoint focused → touched")
            self._mp_touched = True
        elif event.input.id == "f_hc_host":
            logger.debug("AddMountScreen: hc_host focused → touched")
            self._hc_touched = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        logger.debug("AddMountScreen.on_button_pressed: %r", event.button.id)
        if event.button.id == "btn_cancel":
            self.app.pop_screen()
        elif event.button.id == "btn_create":
            self._submit()
        elif event.button.id == "btn_test_ssh":
            self._run_ssh_test()
        elif event.button.id == "btn_browse_remote":
            self._run_remote_browse()

    def _run_ssh_test(self) -> None:
        remote = self.query_one("#f_remote", Input).value.strip()
        if not remote:
            self.app.notify("Enter a Remote first", severity="warning")
            return
        host = parse_remote_host(remote)
        result_label = self.query_one("#ssh-test-result", Label)
        result_label.update("Testing…")
        result_label.styles.color = "yellow"
        logger.debug("AddMountScreen: testing SSH connection to %r", host)
        self._test_ssh(host)

    def _run_remote_browse(self) -> None:
        remote = self.query_one("#f_remote", Input).value.strip()
        if not remote:
            self.app.notify("Enter a Remote first", severity="warning")
            return
        # Build SSH target: keep user@host, strip :path
        host = parse_remote_host(remote)
        user_host = host
        # If remote has user@, include that
        at = remote.find("@")
        colon = remote.find(":")
        if at != -1 and (colon == -1 or at < colon):
            user_host = remote[:colon] if colon != -1 else remote
        # Initial path: use whatever is after the colon, or ~ (home)
        initial = remote[colon + 1:] if colon != -1 else "~"
        if not initial:
            initial = "~"
        logger.debug("AddMountScreen: browse remote target=%r initial=%r", user_host, initial)

        def _on_browse_result(path: str | None) -> None:
            if path is None:
                return
            # Reconstruct remote as user@host:path or host:path
            new_remote = f"{user_host}:{path}"
            logger.debug("AddMountScreen: browser returned %r → remote=%r", path, new_remote)
            self.query_one("#f_remote", Input).value = new_remote

        self.app.push_screen(RemotePathBrowserScreen(user_host, initial), _on_browse_result)

    def _get(self, field_id: str) -> str:
        return self.query_one(f"#{field_id}", Input).value.strip()

    def _submit(self) -> None:
        name   = self._get("f_name") if not self._edit_mode else self._source.name
        remote = self._get("f_remote")
        logger.debug("AddMountScreen._submit: name=%r remote=%r edit=%s", name, remote, self._edit_mode)

        if not name or not remote:
            self.app.notify("Name and Remote are required", severity="error")
            return
        if not self._edit_mode and conf_for(name).exists():
            self.app.notify(f"Mount '{name}' already exists", severity="error")
            return

        mountpoint = self._get("f_mountpoint") or str(get_mount_root() / name)
        hc_host    = self._get("f_hc_host") or ssh_config_hostname(parse_remote_host(remote))

        cfg = MountConfig(
            name=name,
            remote=remote,
            mountpoint=mountpoint,
            retry_secs=int(self._get("f_retry") or "120"),
            connect_timeout=int(self._get("f_timeout") or "10"),
            sshfs_opts=self._get("f_opts") or
                "reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no",
            healthcheck_enabled=self.query_one("#f_hc_enabled", Switch).value,
            healthcheck_host=hc_host,
            healthcheck_mode="tcp" if self.query_one("#f_hc_tcp", Switch).value else "ping",
            healthcheck_port=int(self._get("f_hc_port") or "22"),
            healthcheck_fails=int(self._get("f_hc_fails") or "3"),
            ping_timeout=int(self._get("f_hc_ping") or "2"),
            notifications_enabled=self.query_one("#f_notifications", Switch).value,
            group=self._get("f_group"),
        )
        action_after = self.query_one("#f_enable_after", Switch).value
        if self._edit_mode:
            logger.debug("_submit: saving %s  restart=%s", cfg, action_after)
            self._save(cfg, self._source.mountpoint, action_after)
        else:
            logger.debug("_submit: creating %s  enable_after=%s", cfg, action_after)
            self._create(cfg, action_after)

    @work(thread=True)
    def _test_ssh(self, host: str) -> None:
        ok, msg = test_ssh_connection(host)
        logger.debug("AddMountScreen._test_ssh(%r): ok=%s msg=%r", host, ok, msg)

        def update() -> None:
            label = self.query_one("#ssh-test-result", Label)
            label.update(f"✓ {msg}" if ok else f"✗ {msg}")
            label.styles.color = "green" if ok else "red"

        self.app.call_from_thread(update)

    @work(thread=True)
    def _create(self, cfg: MountConfig, enable_after: bool) -> None:
        logger.debug("AddMountScreen._create: name=%r enable_after=%s", cfg.name, enable_after)
        try:
            Path(cfg.mountpoint).mkdir(parents=True, exist_ok=True)
            write_conf(cfg)
            mp_for(cfg.name).write_text(cfg.mountpoint + "\n")
            ensure_local_link(cfg.name, cfg.mountpoint)
            reload_user_daemon()

            if enable_after:
                r = systemctl_user("enable", "--now", unit_for(cfg.name))
                if r.returncode == 0:
                    logger.debug("  enabled and started %r", cfg.name)
                    msg = f"Created and started mount '{cfg.name}'"
                else:
                    logger.debug("  enable failed: %s", r.stderr.strip())
                    msg = f"Created mount '{cfg.name}' (enable failed: {r.stderr.strip()})"
            else:
                msg = f"Created mount '{cfg.name}'"

            logger.debug("  done: %r", msg)
            self.app.call_from_thread(self.app.notify, msg, severity="information")
            self.app.call_from_thread(self.app.pop_screen)
        except Exception as exc:
            logger.debug("  _create error: %s", exc, exc_info=True)
            self.app.call_from_thread(self.app.notify, str(exc), severity="error")

    @work(thread=True)
    def _save(self, cfg: MountConfig, old_mountpoint: str, restart: bool) -> None:
        logger.debug("AddMountScreen._save: name=%r restart=%s", cfg.name, restart)
        try:
            if old_mountpoint and old_mountpoint != cfg.mountpoint:
                logger.debug("  mountpoint changed: %r → %r", old_mountpoint, cfg.mountpoint)
                systemctl_user("stop", unit_for(cfg.name))
                unmount(old_mountpoint)
            Path(cfg.mountpoint).mkdir(parents=True, exist_ok=True)
            write_conf(cfg)
            mp_for(cfg.name).write_text(cfg.mountpoint + "\n")
            ensure_local_link(cfg.name, cfg.mountpoint)
            reload_user_daemon()

            if restart:
                r = systemctl_user("restart", unit_for(cfg.name))
                if r.returncode == 0:
                    msg = f"Saved and restarted mount '{cfg.name}'"
                else:
                    msg = f"Saved mount '{cfg.name}' (restart failed: {r.stderr.strip()})"
            else:
                msg = f"Saved mount '{cfg.name}'"

            logger.debug("  done: %r", msg)
            self.app.call_from_thread(self.app.notify, msg, severity="information")
            self.app.call_from_thread(self.app.pop_screen)
        except Exception as exc:
            logger.debug("  _save error: %s", exc, exc_info=True)
            self.app.call_from_thread(self.app.notify, str(exc), severity="error")
