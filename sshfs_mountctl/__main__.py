"""Entry point: argument parsing and app launch."""

from __future__ import annotations

import argparse
import sys

from .constants import LOG_FILE
from .logging_ import setup_logging


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sshfs-mountctl",
        description="SSHFS mount manager",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=f"enable debug logging to {LOG_FILE}",
    )
    parser.add_argument(
        "--enable",
        metavar="NAME",
        help="enable and start a mount by name",
    )
    parser.add_argument(
        "--disable",
        metavar="NAME",
        help="stop and disable a mount by name",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="print all mounts with their status",
    )
    parser.add_argument(
        "--status",
        metavar="NAME",
        help="print status for a single mount",
    )
    parser.add_argument(
        "--list-groups",
        action="store_true",
        help="print all group names",
    )
    parser.add_argument(
        "--list-group",
        metavar="GROUP",
        help="print status for all mounts in a group",
    )
    parser.add_argument(
        "--enable-group",
        metavar="GROUP",
        help="enable and start all mounts in a group",
    )
    parser.add_argument(
        "--disable-group",
        metavar="GROUP",
        help="stop and disable all mounts in a group",
    )
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.debug:
        print(f"[debug] logging to {LOG_FILE}", file=sys.stderr)

    # Non-TUI paths
    if args.enable:
        _cmd_enable(args.enable)
    elif args.disable:
        _cmd_disable(args.disable)
    elif args.list:
        _cmd_list()
    elif args.status:
        _cmd_status(args.status)
    elif args.list_groups:
        _cmd_list_groups()
    elif args.list_group:
        _cmd_list_group(args.list_group)
    elif args.enable_group:
        _cmd_enable_group(args.enable_group)
    elif args.disable_group:
        _cmd_disable_group(args.disable_group)
    else:
        from .app import SshfsMountCtl
        SshfsMountCtl().run()


def _cmd_enable(name: str) -> None:
    from .system import conf_for, enable_mount_by_name, list_mount_names
    if name not in list_mount_names():
        print(f"error: no mount named '{name}'", file=sys.stderr)
        sys.exit(1)
    enable_mount_by_name(name)
    print(f"enabled {name}")


def _cmd_disable(name: str) -> None:
    from .system import disable_mount_by_name, list_mount_names
    if name not in list_mount_names():
        print(f"error: no mount named '{name}'", file=sys.stderr)
        sys.exit(1)
    disable_mount_by_name(name)
    print(f"disabled {name}")


def _cmd_list_groups() -> None:
    from .system import list_groups
    groups = list_groups()
    if not groups:
        print("no groups configured")
        return
    for g in groups:
        print(g)


def _cmd_list_group(group: str) -> None:
    from .system import get_mount_status, list_groups, list_mounts_by_group, parse_conf, conf_for
    if group not in list_groups():
        print(f"error: no group named '{group}'", file=sys.stderr)
        sys.exit(1)
    names = list_mounts_by_group(group)
    if not names:
        print(f"no mounts in group '{group}'")
        return
    col = max(len(n) for n in names)
    for name in names:
        st = get_mount_status(name)
        try:
            cfg = parse_conf(conf_for(name))
            remote = cfg.remote
        except Exception:
            remote = "?"
        enabled = "enabled " if st.enabled else "disabled"
        service = st.service_state if st.service_state else "inactive"
        mounted = "mounted  " if st.mounted else "-        "
        print(f"{name:<{col}}  {enabled}  {service:<8}  {mounted}  {remote}")


def _cmd_enable_group(group: str) -> None:
    from .system import enable_group, list_groups
    if group not in list_groups():
        print(f"error: no group named '{group}'", file=sys.stderr)
        sys.exit(1)
    names = enable_group(group)
    for name in names:
        print(f"enabled {name}")


def _cmd_disable_group(group: str) -> None:
    from .system import disable_group, list_groups
    if group not in list_groups():
        print(f"error: no group named '{group}'", file=sys.stderr)
        sys.exit(1)
    names = disable_group(group)
    for name in names:
        print(f"disabled {name}")


def _cmd_list() -> None:
    from .system import get_mount_status, list_mount_names, parse_conf, conf_for
    names = list_mount_names()
    if not names:
        print("no mounts configured")
        return
    col = max(len(n) for n in names)
    for name in names:
        st = get_mount_status(name)
        try:
            cfg = parse_conf(conf_for(name))
            remote = cfg.remote
            group = cfg.group or "-"
        except Exception:
            remote = "?"
            group = "-"
        enabled = "enabled " if st.enabled else "disabled"
        service = st.service_state if st.service_state else "inactive"
        mounted = "mounted  " if st.mounted else "-        "
        print(f"{name:<{col}}  {enabled}  {service:<8}  {mounted}  {group:<12}  {remote}")


def _cmd_status(name: str) -> None:
    from .system import get_mount_status, list_mount_names, parse_conf, conf_for
    if name not in list_mount_names():
        print(f"error: no mount named '{name}'", file=sys.stderr)
        sys.exit(1)
    st = get_mount_status(name)
    try:
        cfg = parse_conf(conf_for(name))
        remote = cfg.remote
        mountpoint = cfg.mountpoint
        group = cfg.group or "-"
    except Exception:
        remote = "?"
        mountpoint = "?"
        group = "-"
    print(f"name:       {name}")
    print(f"remote:     {remote}")
    print(f"mountpoint: {mountpoint}")
    print(f"group:      {group}")
    print(f"enabled:    {'yes' if st.enabled else 'no'}")
    print(f"service:    {st.service_state or 'inactive'}")
    print(f"mounted:    {'yes' if st.mounted else 'no'}")


if __name__ == "__main__":
    main()
