# 🚀 Strompreis MCP — Launch Checklist

## ✅ Done (automated)

- [x] GitHub Repository created — https://github.com/DasClown/strompreis-mcp
- [x] GitHub Discussions enabled
- [x] Issue Templates (Bug Report + Feature Request)
- [x] SQLite database + 15-min data collection cron on server
- [x] MCP Server running (3 tools: price_forecast, best_hours, db_status)
- [x] B2C FastAPI server running on port 8080 (savings calculator)
- [x] 96 SMARD data points collected (growing every 15 min)
- [x] Reddit post draft saved at `deploy/reddit-post.md`

## 📋 Needs your manual action

### 1. Smithery Publishing (5 min)
```
1. Visit https://smithery.ai/new
2. Sign in with GitHub
3. Server type: "Install via pip"
4. Install command: pip install strompreis-mcp
5. Run command: strompreis-mcp
6. Tools: price_forecast, best_hours, db_status
7. Namespace: DasClown
```
Then update the Smithery badge URL in README.md.

### 2. Awin Affiliate Account (15 min)
```
1. Go to https://www.awin.com/
2. Sign up as "Partner/Publisher"
3. Search for "Tibber" (merchant ID: 57405)
4. Apply to the program
5. Get your AWIN_ID
6. Update in b2c/server.py: YOUR_AWIN_ID → your actual ID
7. Redeploy B2C server
```

### 3. Reddit Post (5 min)
```
1. Go to https://reddit.com/r/homeassistant/submit
2. Copy title + body from deploy/reddit-post.md
3. Flair: "Project"
4. Optional: crosspost to r/LocalLLaMA, r/ClaudeAI
```

### 4. Domain (optional, 10 min)
Check domain availability and register:
```
stromcheck.de     — might be taken (referenced since 2013)
dynamisch-lohnt-sich.de  — check
strompreis-check.de       — check
strompreis-prognose.de    — check
```

### 5. Smithery CLI Auth (1 min, alternative to web UI)
```bash
smithery auth login
# Visit the URL shown in your browser to authenticate
smithery mcp publish https://github.com/DasClown/strompreis-mcp -n DasClown/strompreis-mcp
```

## 🔄 Cron status (this server)

| Job | Schedule | Status |
|:----|:---------|:-------|
| SMARD data collection | Every 15 min | ✅ Active |
| DB VACUUM | Sunday 03:00 | ✅ Active |
| B2C Website | Port 8080 | ✅ Running |
| MCP Server | CLI (on demand) | ✅ Installed |

## 📊 Current metrics

| Metric | Value |
|:-------|:------|
| DB rows | 96 (growing) |
| Price range | 26.1 – 62.0 ct/kWh |
| Avg price | ~42 ct/kWh |
| B2C Server | http://localhost:8080 |
| Forecast quality | Hour-profile + day-of-week + live trend |

## Next Phase

Once launched and validated (>10 users, >50 GitHub stars):
- ENTSO-E integration (cross-border exchange)
- DWD BrightSky (weather forecast)
- Random Forest ML model
- API tier pricing (€49/€199 per month)
