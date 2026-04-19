"""Dataclasses for mount configuration and runtime status."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MountConfig:
    name: str
    remote: str
    mountpoint: str
    retry_secs: int = 120
    connect_timeout: int = 10
    sshfs_opts: str = "reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no"
    healthcheck_enabled: bool = False
    healthcheck_host: str = ""
    healthcheck_mode: str = "ping"   # "ping" | "tcp"
    healthcheck_port: int = 22
    healthcheck_fails: int = 3
    ping_timeout: int = 2
    notifications_enabled: bool = False
    group: str = ""


@dataclass
class MountStatus:
    enabled: bool = False
    mounted: bool = False
    service_state: str = "inactive"  # "active" | "inactive" | "failed"
