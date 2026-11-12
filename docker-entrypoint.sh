#!/bin/sh
# Sets timezone (so cron fires at local 07:00), starts cron when ENABLE_CRON=1,
# then runs the container command (uvicorn).
set -e

if [ -n "${TZ:-}" ] && [ -f "/usr/share/zoneinfo/$TZ" ]; then
    ln -sf "/usr/share/zoneinfo/$TZ" /etc/localtime
    echo "$TZ" > /etc/timezone
fi

if [ "${ENABLE_CRON:-0}" = "1" ]; then
    [ -d /data ] && touch /data/sync.log
    cron
    echo "[entrypoint] cron started, TZ=${TZ:-UTC}"
fi

exec "$@"
