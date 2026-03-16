#!/usr/bin/env bash
set -euo pipefail

# Usage: sshfs-watchdog.sh /path/to/mount.conf
CONF="${1:-}"
if [[ -z "$CONF" || ! -f "$CONF" ]]; then
  echo "Usage: $0 /path/to/mount.conf" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$CONF"

: "${NAME:?missing NAME}"
: "${REMOTE:?missing REMOTE (e.g. host:/path)}"
: "${MOUNTPOINT:?missing MOUNTPOINT}"
RETRY_SECS="${RETRY_SECS:-120}"
CONNECT_TIMEOUT="${CONNECT_TIMEOUT:-10}"
SSHFS_OPTS="${SSHFS_OPTS:-reconnect,ServerAliveInterval=15,ServerAliveCountMax=3,cache=no}"
HEALTHCHECK_ENABLED="${HEALTHCHECK_ENABLED:-0}"
HEALTHCHECK_MODE="${HEALTHCHECK_MODE:-ping}"
HEALTHCHECK_PORT="${HEALTHCHECK_PORT:-22}"
HEALTHCHECK_FAILS="${HEALTHCHECK_FAILS:-3}"
PING_TIMEOUT="${PING_TIMEOUT:-2}"
NOTIFICATIONS_ENABLED="${NOTIFICATIONS_ENABLED:-0}"
SETTINGS_CONF="${HOME}/.config/sshfs-mounts/settings.conf"
# Save per-mount notification setting before settings.conf can override it
MOUNT_NOTIFICATIONS_ENABLED="$NOTIFICATIONS_ENABLED"
if [[ -f "$SETTINGS_CONF" ]]; then
  # shellcheck disable=SC1090
  source "$SETTINGS_CONF"
fi
GLOBAL_NOTIFICATIONS_ENABLED="${NOTIFICATIONS_ENABLED:-0}"
LOCAL_LINK_DIR="${LOCAL_LINK_DIR:-${HOME}/Mounts}"
LOCAL_LINK_PATH="${LOCAL_LINK_DIR}/${NAME}"

/usr/bin/fusermount3 -uz "$MOUNTPOINT" >/dev/null 2>&1 || true
mkdir -p "$MOUNTPOINT"

log() { echo "[$NAME] $*"; }

notify() {
  if truthy "$GLOBAL_NOTIFICATIONS_ENABLED" && truthy "$MOUNT_NOTIFICATIONS_ENABLED"; then
    notify-send --app-name="sshfs-mountctl" "SSHFS: $NAME" "$1" 2>/dev/null || true
  fi
}

parse_remote_host() {
  local remote="$1"
  local host="${remote%%:*}"

  if [[ "$host" == *"@"* ]]; then
    host="${host##*@}"
  fi

  printf '%s\n' "$host"
}

truthy() {
  case "${1,,}" in
    1|true|yes|on) return 0 ;;
    *) return 1 ;;
  esac
}

HEALTHCHECK_HOST="${HEALTHCHECK_HOST:-$(parse_remote_host "$REMOTE")}"
PING_AVAILABLE=1
NC_AVAILABLE=1
HEALTHCHECK_MISSING_CMD_LOGGED=0

if ! command -v ping >/dev/null 2>&1; then
  PING_AVAILABLE=0
fi
if ! command -v nc >/dev/null 2>&1; then
  NC_AVAILABLE=0
fi

healthcheck_enabled() {
  if ! truthy "$HEALTHCHECK_ENABLED" || [[ -z "$HEALTHCHECK_HOST" ]]; then
    return 1
  fi
  if [[ "$HEALTHCHECK_MODE" == "tcp" ]]; then
    (( NC_AVAILABLE == 1 ))
  else
    (( PING_AVAILABLE == 1 ))
  fi
}

host_reachable() {
  if [[ "$HEALTHCHECK_MODE" == "tcp" ]]; then
    nc -z -w "$PING_TIMEOUT" "$HEALTHCHECK_HOST" "$HEALTHCHECK_PORT" >/dev/null 2>&1
  else
    ping -c 1 -W "$PING_TIMEOUT" "$HEALTHCHECK_HOST" >/dev/null 2>&1
  fi
}

lazy_unmount() {
  /usr/bin/fusermount3 -uz "$MOUNTPOINT" >/dev/null 2>&1 || true
}

ensure_local_link() {
  mkdir -p "$LOCAL_LINK_DIR"
  ln -sfn "$MOUNTPOINT" "$LOCAL_LINK_PATH"
}

remove_local_link() {
  local target=""

  [[ -L "$LOCAL_LINK_PATH" ]] || return 0

  target="$(readlink "$LOCAL_LINK_PATH" 2>/dev/null || true)"
  if [[ -n "$target" && "$target" != "$MOUNTPOINT" ]]; then
    return 0
  fi

  rm -f "$LOCAL_LINK_PATH"
}

consecutive_failures=0

while true; do
  if /usr/bin/mountpoint -q "$MOUNTPOINT"; then
    ensure_local_link

    if healthcheck_enabled; then
      if host_reachable; then
        consecutive_failures=0
      else
        ((consecutive_failures += 1))
        log "healthcheck failed (${consecutive_failures}/${HEALTHCHECK_FAILS}) for ${HEALTHCHECK_HOST}"

        if (( consecutive_failures >= HEALTHCHECK_FAILS )); then
          log "host unreachable, lazy-unmounting stale mount $MOUNTPOINT"
          lazy_unmount

          if /usr/bin/mountpoint -q "$MOUNTPOINT"; then
            log "lazy unmount did not clear $MOUNTPOINT"
          else
            remove_local_link
            consecutive_failures=0
            notify "Disconnected — host unreachable"
          fi
        fi
      fi
    elif truthy "$HEALTHCHECK_ENABLED" && (( HEALTHCHECK_MISSING_CMD_LOGGED == 0 )); then
      if [[ "$HEALTHCHECK_MODE" == "tcp" ]] && (( NC_AVAILABLE == 0 )); then
        log "healthcheck requested (tcp) but nc is not available; skipping offline checks"
        HEALTHCHECK_MISSING_CMD_LOGGED=1
      elif [[ "$HEALTHCHECK_MODE" != "tcp" ]] && (( PING_AVAILABLE == 0 )); then
        log "healthcheck requested (ping) but ping is not available; skipping offline checks"
        HEALTHCHECK_MISSING_CMD_LOGGED=1
      fi
    fi

    sleep "$RETRY_SECS"
    continue
  fi

  remove_local_link

  if healthcheck_enabled && ! host_reachable; then
    if (( consecutive_failures < HEALTHCHECK_FAILS )); then
      ((consecutive_failures += 1))
    fi
    log "host ${HEALTHCHECK_HOST} unreachable; skipping mount attempt (${consecutive_failures}/${HEALTHCHECK_FAILS})"
    sleep "$RETRY_SECS"
    continue
  fi

  consecutive_failures=0
  log "mounting $REMOTE -> $MOUNTPOINT"
  /usr/bin/sshfs "$REMOTE" "$MOUNTPOINT" \
    -o "ConnectTimeout=${CONNECT_TIMEOUT},${SSHFS_OPTS}" \
    -o "idmap=user,uid=$(id -u),gid=$(id -g),umask=022" || true
  if /usr/bin/mountpoint -q "$MOUNTPOINT"; then
    ensure_local_link
    notify "Connected → $REMOTE"
  fi

  sleep "$RETRY_SECS"
done
