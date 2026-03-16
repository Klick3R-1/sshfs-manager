"""Entry point: argument parsing and app launch."""

from __future__ import annotations

import argparse
import sys

from .constants import LOG_FILE
from .logging_ import setup_logging
from .app import SshfsMountCtl


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
    args = parser.parse_args()

    setup_logging(args.debug)

    if args.debug:
        print(f"[debug] logging to {LOG_FILE}", file=sys.stderr)

    SshfsMountCtl().run()


if __name__ == "__main__":
    main()
