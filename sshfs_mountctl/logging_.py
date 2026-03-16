"""Logging setup. Import `logger` from here in every module."""

from __future__ import annotations

import logging
import sys

from .constants import LOG_FILE

logger = logging.getLogger("sshfs_mountctl")


def setup_logging(debug: bool) -> None:
    if not debug:
        logger.addHandler(logging.NullHandler())
        return
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(LOG_FILE, mode="w")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)-8s [%(module)s.%(funcName)s] %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    logger.debug("=== sshfs-mountctl debug session started ===")
    logger.debug("python %s", sys.version.split()[0])
    logger.debug("log file: %s", LOG_FILE)
