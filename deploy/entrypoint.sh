#!/bin/sh
set -e

SYNC_INTERVAL="${SYNC_INTERVAL:-300}"

if [ -n "$SYNC_REMOTE" ] && [ -n "$SYNC_REMOTE_PATH" ]; then
    echo "Pulling vault from ${SYNC_REMOTE}:${SYNC_REMOTE_PATH}..."
    rclone sync "${SYNC_REMOTE}:${SYNC_REMOTE_PATH}" /vault

    # Background loop: push local changes back to remote
    (
        while true; do
            sleep "$SYNC_INTERVAL"
            echo "Syncing vault to ${SYNC_REMOTE}:${SYNC_REMOTE_PATH}..."
            rclone sync /vault "${SYNC_REMOTE}:${SYNC_REMOTE_PATH}"
        done
    ) &
else
    echo "SYNC_REMOTE not set — skipping sync."
fi

exec uv run python loci_mcp/server.py
