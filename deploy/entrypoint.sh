#!/bin/sh
set -e

# The vault on this machine is the source of truth.
# Nextcloud is a daily backup destination only — no sync, no bisync.

BACKUP_INTERVAL="${BACKUP_INTERVAL:-86400}"  # default: once a day

if [ -n "$BACKUP_REMOTE" ] && [ -n "$BACKUP_REMOTE_PATH" ]; then
    echo "Daily backup enabled: vault → ${BACKUP_REMOTE}:${BACKUP_REMOTE_PATH} every ${BACKUP_INTERVAL}s"
    (
        while true; do
            sleep "$BACKUP_INTERVAL"
            echo "Backing up vault to ${BACKUP_REMOTE}:${BACKUP_REMOTE_PATH}..."
            rclone sync /knowledge-vault "${BACKUP_REMOTE}:${BACKUP_REMOTE_PATH}" --progress \
                && echo "Backup complete." \
                || echo "Backup failed — will retry next interval."
        done
    ) &
else
    echo "BACKUP_REMOTE not set — skipping scheduled backup."
fi

exec uv run python loci_mcp/server.py
