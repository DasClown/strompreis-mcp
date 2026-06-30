# ⚡ Strompreis MCP — Electricity Price Forecast for AI Agents

[![Python ≥3.11](https://img.shields.io/badge/python-%3E%3D3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Smithery](https://img.shields.io/badge/Smithery-Install-7C3AED)](https://smithery.ai/server/strompreis-mcp)

**MCP server that gives AI agents real-time German electricity price forecasts.**  
Tells your smart home agent when to run the dishwasher, charge the car, or schedule power-hungry tasks.

Built for the [Model Context Protocol](https://modelcontextprotocol.io) — works with Claude Desktop, Cline, and any MCP-compatible client.

---

## Architecture

```
                    ┌────────────────────────────┐
                    │    SMARD (Bundesnetzagentur) │
                    │    Live-Strompreise 15min    │
                    └──────────┬─────────────────┘
                               │ API
                    ┌──────────▼─────────────────┐
                    │   strompreis-collector       │
                    │   (Cron: every 15 min)       │
                    └──────────┬─────────────────┘
                               │ writes
                    ┌──────────▼─────────────────┐
                    │   SQLite Database             │
                    │   ~/.strompreis/strompreis.db │
                    │   ├── price_data (historical) │
                    │   ├── api_keys (auth)         │
                    │   └── usage_log (rate limit)  │
                    └──────────┬─────────────────┘
                               │ reads
              ┌────────────────┼────────────────┐
              │                │                 │
    ┌─────────▼──────┐  ┌─────▼──────┐  ┌──────▼─────────┐
    │  MCP Server     │  │  B2C Site   │  │  CLI Tools     │
    │  (stdio/SSE)    │  │  (FastAPI)  │  │  status/vacuum │
    │  price_forecast │  │  savings    │  │                 │
    │  best_hours     │  │  checker    │  │                 │
    │  db_status      │  │  affiliate  │  │                 │
    └─────────────────┘  └────────────┘  └─────────────────┘
```

## Quick Start

### 1. Install

```bash
pip install strompreis-mcp
```

Or from source:
```bash
git clone https://github.com/DasClown/strompreis-mcp.git
cd strompreis-mcp
pip install -e .
```

### 2. Initialize database + first data collection

```bash
# Automatic setup
bash scripts/setup.sh

# Or manual:
strompreis-collector collect
strompreis-collector status
```

### 3. Add to Claude Desktop

Edit `~/.config/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "strompreis": {
      "command": "strompreis-mcp"
    }
  }
}
```

Or with Cline / any MCP client:
```json
{
  "mcpServers": {
    "strompreis": {
      "command": "strompreis-mcp",
      "args": []
    }
  }
}
```

## Tools

| Tool | Parameters | Returns |
|:-----|:-----------|:--------|
| `price_forecast` | `hours` (1-72, default 24) | JSON array: `[{timestamp, price_ct, confidence, is_peak}]` |
| `best_hours` | `count` (default 3) | Human-readable cheapest hours recommendation |
| `db_status` | _none_ | Database health: rows, latest timestamp, usage stats |

### Example Prompts

> *"When is the cheapest time to run my laundry today?"*  
> → Agent calls `best_hours(count=3)` → "Tonight 00:00-02:00 at ~28 ct/kWh"

> *"What's the electricity price forecast for tomorrow?"*  
> → Agent calls `price_forecast(hours=48)` → hourly prices in ct/kWh

> *"Should I charge my EV now or wait?"*  
> → Agent calls `price_forecast(hours=24)`, finds cheapest window

## Database Persistence

The database lives at `~/.strompreis/strompreis.db`. It persists:

| Table | Purpose | Retention |
|:------|:--------|:----------|
| `price_data` | Historical SMARD prices + generation data | Unlimited (for ML training) |
| `api_keys` | Monetization: tier-based API access | Manual expiration |
| `usage_log` | Rate limiting + analytics | Accumulates |

### Cron Setup (recommended)

```bash
# Fetch data every 15 minutes
*/15 * * * * cd /path/to/strompreis-mcp && strompreis-collector collect

# Weekly database maintenance (Sunday 03:00)
0 3 * * 0 cd /path/to/strompreis-mcp && strompreis-collector vacuum
```

Or use the provided crontab:
```bash
crontab deploy/crontab
```

### CLI Commands

```bash
# Fetch + store latest SMARD data
strompreis-collector collect

# Show database health
strompreis-collector status
# → 📊 Strompreis DB Status
#     Total rows:     1,248
#     Latest data:    2026-06-30T21:00:00+00:00
#     DB file size:   180 KB

# Weekly maintenance
strompreis-collector vacuum
```

## Deployment

### systemd (production)

```bash
# Edit deploy/strompreis-mcp.service paths for your system, then:
sudo cp deploy/strompreis-mcp.service /etc/systemd/system/
sudo systemctl enable --now strompreis-mcp

# Monitor
journalctl -u strompreis-mcp -f
```

### B2C Website (side-stream)

```bash
# Install dependencies
pip install strompreis-mcp[b2c]

# Run
python3 -m uvicorn b2c.server:app --host 0.0.0.0 --port 8080
```

Then open `http://localhost:8080` — users enter their annual kWh consumption and get:
- ✅ Savings calculation (fixed vs dynamic tariff)
- ✅ Tibber/Awattar affiliate comparison
- ✅ 24h price forecast snippet

### Smithery

[![Smithery](https://img.shields.io/badge/Smithery-Install-7C3AED)](https://smithery.ai/server/strompreis-mcp)

One-click install for Claude Desktop via Smithery.

## API Key Mode (for production)

By default the server runs in **keyless mode** (100 req/day global limit).  
For production use, set an API key:

```bash
# Generate a key
python3 -c "
from strompreis_mcp.database import create_api_key
print(create_api_key('my-app', tier='pro', daily_limit=10000))
"

# Set it
export STROMPREIS_API_KEY=sp_your_key_here
strompreis-mcp
```

In keyed mode:
- All requests validated against `api_keys` table
- Per-key daily rate limiting
- Usage logged to `usage_log` table

## Data Sources

| Source | Provider | API | Data |
|:-------|:---------|:---:|:-----|
| Day-ahead auction prices | [SMARD (BNetzA)](https://www.smard.de) | [Open REST](https://www.smard.de/app/chart_data/122/DE-LU/) | Live, 15-min resolution |
| Solar generation | SMARD | Chart API | Live, hourly |
| Wind generation | SMARD | Chart API | Live, hourly |
| Grid load | SMARD | Chart API | Live, hourly |

**Planned for v0.3:**
- ENTSO-E Transparency (cross-border exchange, network constraints)
- DWD BrightSky (weather: solar radiation, wind speed, temperature)
- ML model (Random Forest on accumulated DB data)

## License

MIT

---

Built by [@DasClown](https://github.com/DasClown) — German electricity prices for AI agents.
