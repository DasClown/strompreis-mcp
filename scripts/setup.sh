#!/bin/bash
# ⚡ Strompreis MCP — One-command deployment setup
# Usage: bash scripts/setup.sh [--b2c] [--systemd]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()   { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }

INSTALL_DIR="${INSTALL_DIR:-$HOME/strompreis-mcp}"
B2C_MODE=false
SYSTEMD_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --b2c) B2C_MODE=true; shift ;;
        --systemd) SYSTEMD_MODE=true; shift ;;
        *) err "Unknown option: $1"; exit 1 ;;
    esac
done

echo "╔══════════════════════════════════════╗"
echo "║   ⚡ Strompreis MCP — Setup           ║"
echo "╚══════════════════════════════════════╝"

# ─── Install package ──────────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    log "Installing from $INSTALL_DIR"
    cd "$INSTALL_DIR"
    pip install -e . 2>&1 | tail -1
else
    log "Installing from PyPI (not yet published — cloning from GitHub)"
    pip install git+https://github.com/DasClown/strompreis-mcp.git 2>&1 | tail -1
fi

# ─── Verify installation ──────────────────────────────────
if command -v strompreis-mcp &>/dev/null; then
    log "strompreis-mcp installed: $(strompreis-mcp 2>&1 | head -1 || echo 'OK')"
else
    warn "strompreis-mcp not in PATH — check pip install"
fi

if command -v strompreis-collector &>/dev/null; then
    log "strompreis-collector installed"
fi

# ─── Initialize database ──────────────────────────────────
log "Initializing database..."
python3 -c "
from strompreis_mcp import database
database.init_db()
print(f'  DB: {database.DB_PATH}')
print(f'  Size: {__import__(\"os\").path.getsize(database.DB_PATH)} bytes')
"

# ─── First data collection ────────────────────────────────
log "Running first data collection..."
strompreis-collector collect 2>&1 || warn "First collection failed — SMARD may have no new data"
strompreis-collector status 2>&1 || true

# ─── Set up cron ──────────────────────────────────────────
CRON_JOB="*/15 * * * * cd $INSTALL_DIR && strompreis-collector collect >/dev/null 2>&1"
(crontab -l 2>/dev/null | grep -v strompreis-collector; echo "$CRON_JOB") | crontab -
log "Cron: every 15 min data collection"

# Weekly vacuum
WEEKLY="0 3 * * 0 cd $INSTALL_DIR && strompreis-collector vacuum >/dev/null 2>&1"
(crontab -l 2>/dev/null | grep -v 'strompreis-collector vacuum'; echo "$WEEKLY") | crontab -
log "Cron: weekly VACUUM (Sunday 03:00)"

# ─── systemd service ──────────────────────────────────────
if $SYSTEMD_MODE; then
    SERVICE_FILE="/etc/systemd/system/strompreis-mcp.service"
    if [ -f "$INSTALL_DIR/deploy/strompreis-mcp.service" ]; then
        log "Installing systemd service..."
        sudo cp "$INSTALL_DIR/deploy/strompreis-mcp.service" "$SERVICE_FILE"
        sudo sed -i "s|/home/pi/strompreis-mcp|$INSTALL_DIR|g" "$SERVICE_FILE"
        sudo systemctl daemon-reload
        sudo systemctl enable strompreis-mcp
        sudo systemctl start strompreis-mcp || warn "Service failed to start — check 'journalctl -u strompreis-mcp'"
        log "systemd service: active"
    else
        warn "Service file not found — skipping systemd"
    fi
fi

# ─── B2C site ──────────────────────────────────────────────
if $B2C_MODE; then
    log "Installing B2C dependencies..."
    pip install fastapi uvicorn 2>&1 | tail -1

    if $SYSTEMD_MODE; then
        # Install B2C service too
        SERVICE_FILE2="/etc/systemd/system/strompreis-b2c.service"
        if [ -f "$INSTALL_DIR/deploy/strompreis-b2c.service" ]; then
            sudo cp "$INSTALL_DIR/deploy/strompreis-b2c.service" "$SERVICE_FILE2"
            sudo sed -i "s|/home/pi/strompreis-mcp|$INSTALL_DIR|g" "$SERVICE_FILE2"
            sudo systemctl daemon-reload
            sudo systemctl enable strompreis-b2c
            sudo systemctl start strompreis-b2c || warn "B2C service failed to start"
            log "B2C service installed"
        fi
    fi
fi

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   ✅ Setup complete                   ║"
echo "╠══════════════════════════════════════╣"
echo "║  DB: $HOME/.strompreis/strompreis.db"
echo "║  Cron: every 15 min                  ║"
if $SYSTEMD_MODE; then
echo "║  MCP: systemctl status strompreis-mcp ║"
fi
echo "║  Test: strompreis-collector status   ║"
echo "╚══════════════════════════════════════╝"
