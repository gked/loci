#!/usr/bin/env bash
# sync.sh — sync the Loci vault to/from a remote provider via rclone.
#
# Usage:
#   ./sync.sh [direction] [remote]
#
#   direction: push (default), pull, bisync
#   remote:    rclone remote name — overrides config and LOCI_REMOTE
#
# First-time bisync requires: rclone bisync <local> <remote> --resync
#
# Environment overrides:
#   LOCI_VAULT_ROOT   local vault path
#   LOCI_REMOTE       rclone remote name
#   LOCI_REMOTE_PATH  path on the remote

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/../config.yml"

# --- resolve vault root ---
if [[ -n "${LOCI_VAULT_ROOT:-}" ]]; then
    VAULT_ROOT="$LOCI_VAULT_ROOT"
elif command -v python3 &>/dev/null && [[ -f "$CONFIG" ]]; then
    VAULT_ROOT="$(python3 -c "import yaml; print(yaml.safe_load(open('$CONFIG'))['vault_root'])")"
else
    echo "Error: cannot determine vault root. Set LOCI_VAULT_ROOT or ensure config.yml exists." >&2
    exit 1
fi

# --- resolve remote ---
if [[ -n "${2:-}" ]]; then
    REMOTE="$2"
elif [[ -n "${LOCI_REMOTE:-}" ]]; then
    REMOTE="$LOCI_REMOTE"
elif command -v python3 &>/dev/null && [[ -f "$CONFIG" ]]; then
    REMOTE="$(python3 -c "import yaml; c=yaml.safe_load(open('$CONFIG')); print(c.get('sync_remote') or '')")"
else
    REMOTE=""
fi

if [[ -z "$REMOTE" ]]; then
    echo "Error: no rclone remote configured. Set sync_remote in config.yml or pass as argument." >&2
    exit 1
fi

REMOTE_PATH="${LOCI_REMOTE_PATH:-$(python3 -c "import yaml; c=yaml.safe_load(open('$CONFIG')); print(c.get('sync_remote_path', 'loci'))" 2>/dev/null || echo "loci")}"
DIRECTION="${1:-push}"

echo "Loci sync: $DIRECTION  |  local: $VAULT_ROOT  |  remote: $REMOTE:$REMOTE_PATH"

case "$DIRECTION" in
    push)
        rclone sync "$VAULT_ROOT" "$REMOTE:$REMOTE_PATH" --progress
        ;;
    pull)
        rclone sync "$REMOTE:$REMOTE_PATH" "$VAULT_ROOT" --progress
        ;;
    bisync)
        rclone bisync "$VAULT_ROOT" "$REMOTE:$REMOTE_PATH" --progress
        ;;
    *)
        echo "Unknown direction: $DIRECTION. Use push, pull, or bisync." >&2
        exit 1
        ;;
esac

echo "Done."
