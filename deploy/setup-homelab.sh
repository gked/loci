#!/usr/bin/env bash
# setup-homelab.sh — bootstrap loci on a Linux home lab server
#
# Run as root or a user with sudo access:
#   bash setup-homelab.sh
#
# What this does:
#   1. Installs Docker
#   2. Installs rclone (for optional Nextcloud backup)
#   3. Installs cloudflared and sets up a named tunnel
#   4. Clones the loci repo and creates the vault directory
#   5. Writes a .env file for docker-compose
#   6. Starts the loci container

set -euo pipefail

###############################################################################
# Config — edit these before running
###############################################################################

LOCI_REPO="https://github.com/gked/loci.git"
LOCI_DIR="$HOME/loci"
VAULT_DIR="$HOME/loci-vault"
TUNNEL_NAME="loci"
TUNNEL_HOSTNAME="loci.example.com"  # subdomain must be on Cloudflare DNS

# Optional Nextcloud backup — leave blank to skip
BACKUP_REMOTE=""          # rclone remote name, e.g. "nextcloud"
BACKUP_REMOTE_PATH="loci" # folder on the remote

###############################################################################
# Helpers
###############################################################################

info()  { echo "▶ $*"; }
ok()    { echo "✓ $*"; }
warn()  { echo "! $*"; }

require_root_or_sudo() {
    if [ "$EUID" -ne 0 ] && ! sudo -n true 2>/dev/null; then
        echo "This script requires sudo access." >&2
        exit 1
    fi
}

###############################################################################
# 1. Docker
###############################################################################

install_docker() {
    if command -v docker &>/dev/null; then
        ok "Docker already installed: $(docker --version)"
        return
    fi
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    ok "Docker installed. NOTE: log out and back in for group membership to take effect."
    ok "Or run: newgrp docker"
}

###############################################################################
# 2. rclone
###############################################################################

install_rclone() {
    if command -v rclone &>/dev/null; then
        ok "rclone already installed: $(rclone --version | head -1)"
        return
    fi
    info "Installing rclone..."
    curl https://rclone.org/install.sh | sudo bash
    ok "rclone installed."
}

configure_rclone() {
    if [ -z "$BACKUP_REMOTE" ]; then
        warn "BACKUP_REMOTE not set — skipping rclone config."
        warn "If you want Nextcloud backup, run: rclone config"
        return
    fi

    if rclone listremotes | grep -q "^${BACKUP_REMOTE}:"; then
        ok "rclone remote '${BACKUP_REMOTE}' already configured."
        return
    fi

    info "Launching interactive rclone config for remote '${BACKUP_REMOTE}'..."
    info "Choose: webdav → nextcloud → enter your Nextcloud URL and app password"
    rclone config
}

###############################################################################
# 3. cloudflared
###############################################################################

install_cloudflared() {
    if command -v cloudflared &>/dev/null; then
        ok "cloudflared already installed: $(cloudflared --version)"
        return
    fi
    info "Installing cloudflared..."
    local arch
    arch=$(uname -m)
    case "$arch" in
        x86_64)  local bin="cloudflared-linux-amd64" ;;
        aarch64) local bin="cloudflared-linux-arm64" ;;
        armv7l)  local bin="cloudflared-linux-arm"   ;;
        *)       echo "Unsupported arch: $arch" >&2; exit 1 ;;
    esac
    curl -L "https://github.com/cloudflare/cloudflared/releases/latest/download/${bin}" \
        -o /tmp/cloudflared
    sudo install /tmp/cloudflared /usr/local/bin/cloudflared
    ok "cloudflared installed."
}

setup_cloudflare_tunnel() {
    info "Setting up Cloudflare Tunnel '${TUNNEL_NAME}'..."

    # Login — opens a browser, saves cert to ~/.cloudflared/cert.pem
    if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
        info "Logging in to Cloudflare (browser will open)..."
        cloudflared tunnel login
    else
        ok "Already logged in to Cloudflare."
    fi

    # Create tunnel if it doesn't exist
    if cloudflared tunnel list 2>/dev/null | grep -q "$TUNNEL_NAME"; then
        ok "Tunnel '${TUNNEL_NAME}' already exists."
    else
        cloudflared tunnel create "$TUNNEL_NAME"
        ok "Tunnel '${TUNNEL_NAME}' created."
    fi

    # Write config file
    local tunnel_id
    tunnel_id=$(cloudflared tunnel list --output json 2>/dev/null \
        | python3 -c "import sys,json; tunnels=json.load(sys.stdin); \
          print(next(t['id'] for t in tunnels if t['name']=='${TUNNEL_NAME}'))")

    mkdir -p "$HOME/.cloudflared"
    cat > "$HOME/.cloudflared/config.yml" <<EOF
tunnel: ${tunnel_id}
credentials-file: ${HOME}/.cloudflared/${tunnel_id}.json

ingress:
  - hostname: ${TUNNEL_HOSTNAME}
    service: http://localhost:4444
  - service: http_status:404
EOF

    ok "Cloudflare tunnel config written to ~/.cloudflared/config.yml"

    # Route DNS
    info "Routing ${TUNNEL_HOSTNAME} → tunnel (requires domain on Cloudflare DNS)..."
    cloudflared tunnel route dns "$TUNNEL_NAME" "$TUNNEL_HOSTNAME"
    ok "DNS routed: ${TUNNEL_HOSTNAME}"

    # Install as systemd service
    info "Installing cloudflared as a systemd service..."
    sudo cloudflared service install
    sudo systemctl enable --now cloudflared
    ok "cloudflared service running."
}

###############################################################################
# 4. Loci repo + vault
###############################################################################

setup_loci() {
    if [ -d "$LOCI_DIR" ]; then
        ok "Loci repo already at ${LOCI_DIR} — pulling latest..."
        git -C "$LOCI_DIR" pull
    else
        info "Cloning loci repo..."
        git clone "$LOCI_REPO" "$LOCI_DIR"
    fi

    mkdir -p "$VAULT_DIR"
    ok "Vault directory: ${VAULT_DIR}"

    # Write .env for docker-compose
    local env_file="$LOCI_DIR/deploy/.env"
    if [ -f "$env_file" ]; then
        warn ".env already exists at ${env_file} — skipping."
    else
        cat > "$env_file" <<EOF
VAULT_PATH=${VAULT_DIR}
RCLONE_CONFIG=${HOME}/.config/rclone/rclone.conf
BACKUP_REMOTE=${BACKUP_REMOTE}
BACKUP_REMOTE_PATH=${BACKUP_REMOTE_PATH}
BACKUP_INTERVAL=86400
EOF
        ok ".env written to ${env_file}"
    fi
}

###############################################################################
# 5. Start the container
###############################################################################

start_loci() {
    info "Building and starting loci container..."
    cd "$LOCI_DIR/deploy"
    docker compose --env-file .env up -d --build
    ok "Loci MCP server running on localhost:8000"
}

###############################################################################
# Main
###############################################################################

main() {
    require_root_or_sudo

    echo ""
    echo "════════════════════════════════════════"
    echo "  Loci Home Lab Setup"
    echo "════════════════════════════════════════"
    echo ""

    install_docker
    install_rclone
    configure_rclone
    install_cloudflared
    setup_cloudflare_tunnel
    setup_loci
    start_loci

    echo ""
    echo "════════════════════════════════════════"
    echo "  Done!"
    echo ""
    echo "  MCP server: http://localhost:4444/sse"
    echo "  Tunnel URL: check cloudflared tunnel info ${TUNNEL_NAME}"
    echo ""
    echo "  Next steps:"
    echo ""
    echo "  Tunnel URL: https://${TUNNEL_HOSTNAME}/sse"
    echo ""
    echo "  1. Protect with Cloudflare Zero Trust (do this now — endpoint is currently open):"
    echo "     a. https://one.dash.cloudflare.com → Access → Applications → Add application"
    echo "     b. Self-hosted → Application domain: ${TUNNEL_HOSTNAME}"
    echo "     c. Policy: Allow → Emails → your email address"
    echo "     d. Save."
    echo ""
    echo "  2. Connect clients:"
    echo "     Claude Desktop / Code:"
    echo "       claude mcp add --transport sse loci https://${TUNNEL_HOSTNAME}/sse --scope user"
    echo "     Claude.ai / mobile:"
    echo "       Settings → Connectors → Add custom connector → https://${TUNNEL_HOSTNAME}/sse"
    echo "       (Cloudflare login prompt on first connect)"
    echo "════════════════════════════════════════"
}

main "$@"
