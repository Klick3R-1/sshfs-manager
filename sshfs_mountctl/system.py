"""System-level functions: subprocess wrappers, config I/O, SSH helpers."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import urllib.request
from pathlib import Path

from .constants import (
    EDITOR_CANDIDATES,
    GITHUB_RELEASES_URL,
    UPDATE_CACHE_FILE,
    LOCAL_LINK_DIR,
    MOUNT_ROOT,
    MOUNTS_DIR,
    HOME,
)
from .logging_ import logger
from .models import MountConfig, MountStatus


def _clean_env() -> dict:
    """Restore LD_LIBRARY_PATH for subprocess calls when running as a PyInstaller bundle."""
    env = os.environ.copy()
    orig = env.pop("LD_LIBRARY_PATH_ORIG", None)
    if orig is not None:
        env["LD_LIBRARY_PATH"] = orig
    else:
        env.pop("LD_LIBRARY_PATH", None)
    return env


# ── Settings ─────────────────────────────────────────────────────────────────────

SETTINGS_FILE = MOUNTS_DIR / "settings.conf"


def load_settings() -> dict[str, str]:
    defaults = {
        "LOCAL_LINK_DIR": str(LOCAL_LINK_DIR),
        "MOUNT_ROOT": str(MOUNT_ROOT),
        "NOTIFICATIONS_ENABLED": "0",
    }
    if not SETTINGS_FILE.exists():
        return defaults
    result = dict(defaults)
    for line in SETTINGS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            key, val = line.split("=", 1)
            result[key.strip()] = shlex.split(val.strip())[0]
        except Exception:
            pass
    return result


def save_settings(local_link_dir: str, mount_root: str,
                  notifications_enabled: bool = False) -> None:
    MOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    # Read-modify-write so unknown keys added by future versions are preserved
    current = load_settings()
    current["LOCAL_LINK_DIR"] = local_link_dir
    current["MOUNT_ROOT"] = mount_root
    current["NOTIFICATIONS_ENABLED"] = "1" if notifications_enabled else "0"
    lines = []
    for key, val in current.items():
        # Quote values that contain spaces or are paths
        lines.append(f'{key}="{val}"\n')
    SETTINGS_FILE.write_text("".join(lines))


def get_local_link_dir() -> Path:
    return Path(load_settings()["LOCAL_LINK_DIR"])


def get_mount_root() -> Path:
    return Path(load_settings()["MOUNT_ROOT"])


def migrate_link_dir(old_dir: Path, new_dir: Path) -> list[str]:
    """Move symlinks from old_dir to new_dir. Returns names that were moved."""
    logger.debug("migrate_link_dir: %s → %s", old_dir, new_dir)
    new_dir.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for name in list_mount_names():
        old_link = old_dir / name
        if not old_link.is_symlink():
            continue
        target = Path(os.readlink(old_link))
        new_link = new_dir / name
        if new_link.exists() and not new_link.is_symlink():
            logger.debug("  %s: destination exists and is not a symlink, skipping", name)
            continue
        new_link.unlink(missing_ok=True)
        new_link.symlink_to(target)
        old_link.unlink()
        moved.append(name)
        logger.debug("  moved symlink for %r: %s → %s", name, old_link, new_link)
    return moved


def migrate_mount_root(old_root: Path, new_root: Path) -> list[str]:
    """Re-home mounts whose mountpoint is directly under old_root.

    Active (mounted) mounts are stopped, unmounted, moved, and restarted.
    Enabled-but-idle mounts are stopped, updated, and restarted.
    Disabled mounts just have their conf updated.
    Returns names that were migrated.
    """
    logger.debug("migrate_mount_root: %s → %s", old_root, new_root)
    old_prefix = str(old_root) + "/"
    migrated: list[str] = []
    for name in list_mount_names():
        try:
            cfg = parse_conf(conf_for(name))
        except Exception as exc:
            logger.debug("  %r: could not parse conf: %s", name, exc)
            continue

        if not cfg.mountpoint.startswith(old_prefix):
            logger.debug("  %r: mountpoint %r not under old root, skipping",
                         name, cfg.mountpoint)
            continue

        new_mp = str(new_root / name)
        unit = unit_for(name)
        was_mounted = is_mounted(cfg.mountpoint)
        was_enabled = systemctl_user("is-enabled", "--quiet", unit).returncode == 0

        logger.debug("  %r: mounted=%s enabled=%s  %s → %s",
                     name, was_mounted, was_enabled, cfg.mountpoint, new_mp)

        if was_mounted or was_enabled:
            systemctl_user("stop", unit)
            if was_mounted:
                unmount(cfg.mountpoint)

        Path(new_mp).mkdir(parents=True, exist_ok=True)
        cfg.mountpoint = new_mp
        write_conf(cfg)
        mp_for(name).write_text(new_mp + "\n")

        if was_enabled:
            systemctl_user("start", unit)

        migrated.append(name)
        logger.debug("  migrated %r ok", name)

    return migrated


# ── Path helpers ────────────────────────────────────────────────────────────────

def unit_for(name: str) -> str:
    return f"sshfs-watchdog@{name}.service"


def conf_for(name: str) -> Path:
    return MOUNTS_DIR / f"{name}.conf"


def mp_for(name: str) -> Path:
    return MOUNTS_DIR / f"{name}.mountpoint"


# ── systemd ─────────────────────────────────────────────────────────────────────

def systemctl_user(*args: str) -> subprocess.CompletedProcess:
    cmd = ["systemctl", "--user", *args]
    logger.debug("run: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, env=_clean_env())
    logger.debug("  → rc=%d stdout=%r stderr=%r",
                 r.returncode, r.stdout.strip(), r.stderr.strip())
    return r


def reload_user_daemon() -> None:
    logger.debug("reloading systemd user daemon")
    systemctl_user("daemon-reload")


# ── Mount detection ─────────────────────────────────────────────────────────────

def is_mounted(mountpoint: str) -> bool:
    cmd = ["/usr/bin/findmnt", "-rn", "-M", mountpoint, "-o", "FSTYPE"]
    logger.debug("run: %s", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, env=_clean_env())
    fstype = r.stdout.strip()
    result = bool(fstype) and fstype.startswith("fuse")
    logger.debug("  → fstype=%r  mounted=%s", fstype, result)
    return result


def unmount(mountpoint: str) -> bool:
    logger.debug("unmount(%r)", mountpoint)
    for flags in ["-u", "-uz"]:
        cmd = ["/usr/bin/fusermount3", flags, mountpoint]
        logger.debug("  run: %s", " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True, env=_clean_env())
        logger.debug("  → rc=%d", r.returncode)
        if not is_mounted(mountpoint):
            logger.debug("  → unmounted with fusermount3 %s", flags)
            return True
    cmd = ["/usr/bin/umount", "-l", mountpoint]
    logger.debug("  run (last resort): %s", " ".join(cmd))
    subprocess.run(cmd, capture_output=True, env=_clean_env())
    result = not is_mounted(mountpoint)
    logger.debug("  → unmount result: %s", result)
    return result


# ── Config I/O ──────────────────────────────────────────────────────────────────

def parse_conf(path: Path) -> MountConfig:
    logger.debug("parsing config: %s", path)
    data: dict[str, str] = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, rest = line.partition("=")
            rest = rest.strip()
            try:
                val = shlex.split(rest)[0] if rest else ""
            except ValueError:
                val = rest.strip('"').strip("'")
            data[key.strip()] = val

    cfg = MountConfig(
        name=data.get("NAME", ""),
        remote=data.get("REMOTE", ""),
        mountpoint=data.get("MOUNTPOINT", ""),
        retry_secs=int(data.get("RETRY_SECS", 120)),
        connect_timeout=int(data.get("CONNECT_TIMEOUT", 10)),
        sshfs_opts=data.get("SSHFS_OPTS",
            "reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no"),
        healthcheck_enabled=data.get("HEALTHCHECK_ENABLED", "0") == "1",
        healthcheck_host=data.get("HEALTHCHECK_HOST", ""),
        healthcheck_mode=data.get("HEALTHCHECK_MODE", "ping"),
        healthcheck_port=int(data.get("HEALTHCHECK_PORT", 22)),
        healthcheck_fails=int(data.get("HEALTHCHECK_FAILS", 3)),
        ping_timeout=int(data.get("PING_TIMEOUT", 2)),
        notifications_enabled=data.get("NOTIFICATIONS_ENABLED", "0") == "1",
        group=data.get("GROUP", ""),
    )
    logger.debug("  → name=%r remote=%r mountpoint=%r hc_enabled=%s",
                 cfg.name, cfg.remote, cfg.mountpoint, cfg.healthcheck_enabled)
    return cfg


def write_conf(cfg: MountConfig) -> None:
    path = conf_for(cfg.name)
    logger.debug("writing config: %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(f'NAME="{cfg.name}"\n')
        f.write(f'REMOTE="{cfg.remote}"\n')
        f.write(f'MOUNTPOINT="{cfg.mountpoint}"\n')
        f.write(f'RETRY_SECS={cfg.retry_secs}\n')
        f.write(f'CONNECT_TIMEOUT={cfg.connect_timeout}\n')
        f.write(f'SSHFS_OPTS="{cfg.sshfs_opts}"\n')
        f.write(f'HEALTHCHECK_ENABLED={1 if cfg.healthcheck_enabled else 0}\n')
        f.write(f'HEALTHCHECK_HOST="{cfg.healthcheck_host}"\n')
        f.write(f'HEALTHCHECK_MODE="{cfg.healthcheck_mode}"\n')
        f.write(f'HEALTHCHECK_PORT={cfg.healthcheck_port}\n')
        f.write(f'HEALTHCHECK_FAILS={cfg.healthcheck_fails}\n')
        f.write(f'PING_TIMEOUT={cfg.ping_timeout}\n')
        f.write(f'NOTIFICATIONS_ENABLED={1 if cfg.notifications_enabled else 0}\n')
        if cfg.group:
            f.write(f'GROUP="{cfg.group}"\n')
    logger.debug("  → written ok")


def list_mount_names() -> list[str]:
    MOUNTS_DIR.mkdir(parents=True, exist_ok=True)
    names = sorted(p.stem for p in MOUNTS_DIR.glob("*.conf")
                   if p.name != SETTINGS_FILE.name)
    logger.debug("list_mount_names → %s", names)
    return names


def get_mount_status(name: str) -> MountStatus:
    logger.debug("get_mount_status(%r)", name)
    unit = unit_for(name)
    st = MountStatus()
    st.enabled = systemctl_user("is-enabled", "--quiet", unit).returncode == 0
    if systemctl_user("is-failed", "--quiet", unit).returncode == 0:
        st.service_state = "failed"
    elif systemctl_user("is-active", "--quiet", unit).returncode == 0:
        st.service_state = "active"
    try:
        cfg = parse_conf(conf_for(name))
        st.mounted = is_mounted(cfg.mountpoint)
    except Exception as exc:
        logger.debug("  could not check mounted state: %s", exc)
    logger.debug("  → enabled=%s mounted=%s state=%r",
                 st.enabled, st.mounted, st.service_state)
    return st


# ── SSH helpers ─────────────────────────────────────────────────────────────────

def parse_remote_host(remote: str) -> str:
    host = remote.split(":")[0]
    result = host.split("@")[-1] if "@" in host else host
    logger.debug("parse_remote_host(%r) → %r", remote, result)
    return result


def ssh_config_hostname(alias: str) -> str:
    """Return the HostName directive for an SSH alias, or the alias itself."""
    logger.debug("ssh_config_hostname(%r)", alias)
    ssh_dir = HOME / ".ssh"

    def _parse_file(path: Path) -> str | None:
        if not path.exists():
            return None
        current_hosts: list[str] = []
        with open(path) as f:
            for line in f:
                stripped = line.strip()
                lower = stripped.lower()
                if lower.startswith("include "):
                    pattern = os.path.expanduser(stripped[8:].strip())
                    if not pattern.startswith("/"):
                        pattern = str(ssh_dir / pattern)
                    for inc in sorted(Path("/").glob(pattern.lstrip("/"))):
                        result = _parse_file(inc)
                        if result is not None:
                            return result
                elif lower.startswith("host "):
                    current_hosts = stripped[5:].split()
                elif lower.startswith("hostname ") and alias in current_hosts:
                    return stripped.split(None, 1)[1]
        return None

    result = _parse_file(HOME / ".ssh" / "config")
    logger.debug("  → %r", result or alias)
    return result or alias


def ssh_config_hosts() -> list[str]:
    """Return all non-wildcard Host entries from ~/.ssh/config (follows Include)."""
    logger.debug("ssh_config_hosts: scanning ~/.ssh/config")
    hosts: list[str] = []
    seen: set[str] = set()
    ssh_dir = HOME / ".ssh"

    def _parse_file(path: Path) -> None:
        if not path.exists():
            logger.debug("  ssh config not found: %s", path)
            return
        logger.debug("  parsing: %s", path)
        with open(path) as f:
            for line in f:
                stripped = line.strip()
                lower = stripped.lower()
                if lower.startswith("include "):
                    pattern = os.path.expanduser(stripped[8:].strip())
                    if not pattern.startswith("/"):
                        pattern = str(ssh_dir / pattern)
                    for inc in sorted(Path("/").glob(pattern.lstrip("/"))):
                        _parse_file(inc)
                elif lower.startswith("host "):
                    for host in stripped[5:].split():
                        if "*" not in host and "?" not in host and host not in seen:
                            seen.add(host)
                            hosts.append(host)

    _parse_file(HOME / ".ssh" / "config")
    logger.debug("ssh_config_hosts: found %d hosts", len(hosts))
    return hosts


def test_ssh_connection(host: str, timeout: int = 5) -> tuple[bool, str]:
    """Run a quick SSH connectivity check. Returns (success, message)."""
    logger.debug("test_ssh_connection(%r, timeout=%d)", host, timeout)
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout={timeout}",
        "-o", "StrictHostKeyChecking=accept-new",
        host, "true",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 5, env=_clean_env())
        if r.returncode == 0:
            logger.debug("  → connected ok")
            return True, f"Connected to {host}"
        msg = r.stderr.strip() or f"Connection failed (rc={r.returncode})"
        logger.debug("  → failed: %s", msg)
        return False, msg
    except subprocess.TimeoutExpired:
        logger.debug("  → subprocess timeout")
        return False, f"Timed out after {timeout}s"


def find_editor() -> str:
    for env_var in ("VISUAL", "EDITOR"):
        val = os.environ.get(env_var, "")
        if val and shutil.which(val):
            logger.debug("find_editor: using $%s → %r", env_var, val)
            return val
    for candidate in EDITOR_CANDIDATES:
        if shutil.which(candidate):
            logger.debug("find_editor: found candidate %r", candidate)
            return candidate
    logger.debug("find_editor: falling back to vi")
    return "vi"


# ── Install helpers ─────────────────────────────────────────────────────────────

def is_installed() -> bool:
    from .constants import UNIT_TEMPLATE, WATCHDOG_DST, WATCHDOG_SYSTEM_DST
    watchdog = WATCHDOG_SYSTEM_DST if WATCHDOG_SYSTEM_DST.exists() else WATCHDOG_DST
    checks = {
        "unit_template":       UNIT_TEMPLATE.exists(),
        "watchdog_dst":        watchdog.exists(),
        "watchdog_executable": os.access(watchdog, os.X_OK),
    }
    result = all(checks.values())
    logger.debug("is_installed → %s  checks=%s  watchdog=%s", result, checks, watchdog)
    return result


def ensure_local_link(name: str, mountpoint: str) -> None:
    logger.debug("ensure_local_link(%r, %r)", name, mountpoint)
    link_dir = get_local_link_dir()
    link_dir.mkdir(parents=True, exist_ok=True)
    link = link_dir / name
    if link.exists() and not link.is_symlink():
        raise RuntimeError(f"{link} exists and is not a symlink")
    link.unlink(missing_ok=True)
    link.symlink_to(mountpoint)
    logger.debug("  → symlink %s → %s", link, mountpoint)


def remove_local_link(name: str, mountpoint: str = "") -> None:
    logger.debug("remove_local_link(%r, mountpoint=%r)", name, mountpoint)
    link = get_local_link_dir() / name
    if not link.is_symlink():
        logger.debug("  → not a symlink, skipping")
        return
    if mountpoint:
        try:
            if str(link.resolve()) != mountpoint:
                logger.debug("  → symlink target mismatch, skipping")
                return
        except Exception as exc:
            logger.debug("  → resolve error: %s", exc)
    link.unlink()
    logger.debug("  → removed %s", link)


def enable_mount_by_name(name: str) -> None:
    logger.debug("enable_mount_by_name(%r)", name)
    unit = unit_for(name)
    cfg = parse_conf(conf_for(name))
    Path(cfg.mountpoint).mkdir(parents=True, exist_ok=True)
    ensure_local_link(name, cfg.mountpoint)
    mp_for(name).write_text(cfg.mountpoint + "\n")
    systemctl_user("enable", "--now", unit)


def disable_mount_by_name(name: str) -> None:
    logger.debug("disable_mount_by_name(%r)", name)
    unit = unit_for(name)
    systemctl_user("stop", unit)
    systemctl_user("disable", unit)
    mpfile = mp_for(name)
    if mpfile.exists():
        mp = mpfile.read_text().strip()
        logger.debug("  mountpoint: %r", mp)
        if mp:
            unmount(mp)
            remove_local_link(name, mp)
            if Path(mp).is_dir():
                logger.debug("  attempting rmdir: %s", mp)
                try:
                    Path(mp).rmdir()
                    logger.debug("  rmdir ok")
                except OSError as exc:
                    logger.debug("  rmdir failed: %s", exc)
    else:
        logger.debug("  no .mountpoint file found")


def set_mount_group(name: str, group: str) -> None:
    logger.debug("set_mount_group(%r, %r)", name, group)
    cfg = parse_conf(conf_for(name))
    cfg.group = group
    write_conf(cfg)


def rename_group(old_name: str, new_name: str) -> list[str]:
    """Rename a group across all mounts. Returns names that were updated."""
    updated = []
    for name in list_mount_names():
        try:
            cfg = parse_conf(conf_for(name))
            if cfg.group == old_name:
                cfg.group = new_name
                write_conf(cfg)
                updated.append(name)
        except Exception as exc:
            logger.debug("  rename_group: error on %r: %s", name, exc)
    return updated


def delete_group(group_name: str) -> list[str]:
    """Clear group from all mounts in a group. Returns names that were updated."""
    updated = []
    for name in list_mounts_by_group(group_name):
        try:
            set_mount_group(name, "")
            updated.append(name)
        except Exception as exc:
            logger.debug("  delete_group: error on %r: %s", name, exc)
    return updated


def list_groups() -> list[str]:
    """Return sorted unique group names across all configured mounts."""
    groups: set[str] = set()
    for name in list_mount_names():
        try:
            g = parse_conf(conf_for(name)).group
            if g:
                groups.add(g)
        except Exception:
            pass
    return sorted(groups)


def list_mounts_by_group(group: str) -> list[str]:
    """Return mount names belonging to the given group."""
    members = []
    for name in list_mount_names():
        try:
            if parse_conf(conf_for(name)).group == group:
                members.append(name)
        except Exception:
            pass
    return members


def enable_group(group: str) -> list[str]:
    """Enable all mounts in a group. Returns names that were processed."""
    names = list_mounts_by_group(group)
    for name in names:
        enable_mount_by_name(name)
    return names


def disable_group(group: str) -> list[str]:
    """Disable all mounts in a group. Returns names that were processed."""
    names = list_mounts_by_group(group)
    for name in names:
        disable_mount_by_name(name)
    return names


def ensure_bin_in_path() -> list[str]:
    shell = Path(os.environ.get("SHELL", "")).name
    logger.debug("ensure_bin_in_path: shell=%r", shell)
    export_line = 'export PATH="$HOME/.bin:$PATH"'
    marker = "# Added by sshfs-mountctl installer"
    modified: list[str] = []

    def append_if_missing(target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch()
        content = target.read_text()
        if export_line not in content and marker not in content:
            with open(target, "a") as f:
                f.write(f"\n{marker}\n{export_line}\n")
            modified.append(str(target))
            logger.debug("  appended PATH export to %s", target)
        else:
            logger.debug("  already present in %s", target)

    append_if_missing(HOME / ".profile")
    rc_map = {"bash": HOME / ".bashrc", "zsh": HOME / ".zshrc"}
    if shell in rc_map:
        append_if_missing(rc_map[shell])
    elif shell == "fish":
        fish_cfg = HOME / ".config" / "fish" / "config.fish"
        fish_cfg.parent.mkdir(parents=True, exist_ok=True)
        fish_cfg.touch()
        if "fish_add_path $HOME/.bin" not in fish_cfg.read_text():
            with open(fish_cfg, "a") as f:
                f.write(f"\n{marker}\nfish_add_path $HOME/.bin\n")
            modified.append(str(fish_cfg))
            logger.debug("  appended fish_add_path to %s", fish_cfg)

    logger.debug("ensure_bin_in_path: modified=%s", modified)
    return modified


def check_latest_version(force: bool = False) -> str | None:
    """Return latest release version from GitHub, using a once-per-day cache.

    Returns a version string (e.g. '1.0.2') or None on failure / cache miss.
    Pass force=True to bypass the cache and always fetch from GitHub.
    """
    import time

    try:
        now = time.time()
        if not force and UPDATE_CACHE_FILE.exists():
            cached = json.loads(UPDATE_CACHE_FILE.read_text())
            if now - cached.get("ts", 0) < 86400:
                logger.debug("check_latest_version: using cache (%s)", cached.get("version"))
                return cached.get("version")

        req = urllib.request.Request(
            GITHUB_RELEASES_URL, headers={"User-Agent": "sshfs-mountctl"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        version = data.get("tag_name", "").lstrip("v") or None
        UPDATE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_CACHE_FILE.write_text(json.dumps({"ts": now, "version": version}))
        logger.debug("check_latest_version: fetched %s", version)
        return version
    except Exception as exc:
        logger.debug("check_latest_version: %s", exc)
    return None
