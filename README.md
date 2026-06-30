# ⚡ Strompreis MCP — Electricity Price Forecast for AI Agents

[![Python ≥3.11](https://img.shields.io/badge/python-%3E%3D3.11-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Smithery](https://img.shields.io/badge/Smithery-Install-7C3AED)](https://smithery.ai/server/strompreis-mcp)

**MCP server that gives AI agents real-time German electricity price forecasts.**  
Tells your smart home agent when to run the dishwasher, charge the car, or schedule power-hungry tasks.

## What it does

| Tool | What it answers |
|------|----------------|
| `price_forecast(hours=24)` | "What will electricity cost in the next 24 hours?" |
| `best_hours(count=3)` | "When should I run power-hungry devices today?" |

## Quick Start

```bash
pip install strompreis-mcp
```

Then add to your Claude Desktop config:

```json
{
  "mcpServers": {
    "strompreis": {
      "command": "python3",
      "args": ["-m", "strompreis_mcp.server"]
    }
  }
}
```

## Example Prompts

> "When is the cheapest time to run my laundry today?"
> → Agent calls `best_hours(count=3)` → "14:00–17:00 at ~8.2 ct/kWh"

> "What's the electricity price forecast for tomorrow?"
> → Agent calls `price_forecast(hours=48)` → chart data

## Data Sources

| Source | Provider | Type |
|--------|----------|------|
| Day-ahead auction prices | SMARD (BNetzA) | Live, 15-min resolution |
| Solar/wind generation forecast | ENTSO-E Transparency | Live, hourly |
| Weather forecast | DWD BrightSky | Live, free |

## License

MIT
