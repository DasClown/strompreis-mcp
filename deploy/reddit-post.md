---
# Reddit Post Draft — r/homeassistant
# Post this after Smithery is published
# Instructions:
#   1. Go to https://reddit.com/r/homeassistant/submit
#   2. Title: copy below
#   3. Post body: copy below
#   4. Flair: "Project"
---

## Title

"I built a free MCP server that gives AI agents real-time German electricity prices (SMARD/Bundesnetzagentur)"

## Post Body

Since dynamic electricity tariffs are now mandatory in Germany (§41a EnWG), I built an open-source MCP server that gives AI agents live electricity price forecasts.

**What it does:**
- `price_forecast(hours=24)` → returns hourly prices in ct/kWh with confidence
- `best_hours(count=3)` → tells you the cheapest time to run appliances
- `db_status()` → checks data freshness

**How it works:**
- Fetches live data from SMARD (Bundesnetzagentur) every 15 min
- Stores history in SQLite for better forecasts
- No API key needed for local use (100 calls/day free tier)
- Works with Claude Desktop, Cline, or any MCP client

**Use cases:**
- "When is the cheapest time to charge my car tonight?"
- "Should I run the dishwasher now or wait?"
- "How much could I save with a dynamic tariff?"

**GitHub:** https://github.com/DasClown/strompreis-mcp
**Smithery:** https://smithery.ai/server/strompreis-mcp

```json
// Claude Desktop config
{
  "mcpServers": {
    "strompreis": {
      "command": "pip install strompreis-mcp && strompreis-mcp"
    }
  }
}
```

Built with the exact same pattern as CropProphEU — all data from public APIs, no scraping.

Happy to answer questions or take feature requests!
