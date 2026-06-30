"""
B2C Side-Stream — FastAPI website for stromcheck.de

Two tools, same engine as the MCP server:
  1. / → Landing page with savings calculator
  2. /check → API for savings calculation
  3. /affiliate → Tibber/Awattar redirect
"""

import os
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Form, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

# Reuse Strompreis engine
from strompreis_mcp import forecast, database, smard_client

app = FastAPI(
    title="Stromcheck — Lohnt sich dynamischer Strom?",
    description="Berechne deine Ersparnis mit dynamischem Stromtarif",
    version="0.1.0",
)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Affiliate links for Tibber (via Awin — €30/Sale)
# Sign up at https://www.awin.com/ then apply to Tibber (merchant 57405)
# Replace YOUR_AWIN_ID with your actual Awin publisher ID
AFFILIATE = {
    "tibber": "https://www.awin1.com/cread.php?awinmid=57405&awinaffid=YOUR_AWIN_ID&p=https://tibber.com/de",
    "awattar": "https://www.awattar.at/company/partner",  # Contact: patrick.weltin@awattar.com
}

# German electricity price stats (2026 Q2)
FESTPREIS_AVG = 28.0  # ct/kWh average fixed tariff
BÖRSEN_AUFSCHLAG = 5.5  # ct/kWh markup on exchange price (Tibber/Awattar typical)

@app.get("/", response_class=HTMLResponse)
async def landing_page():
    return HTMLResponse(LANDING_HTML)


@app.get("/check")
async def check_form():
    return HTMLResponse(LANDING_HTML)


@app.post("/check")
async def do_check(
    verbrauch: float = Form(..., ge=500, le=50000),
    plz: str = Form("", max_length=5),
):
    """Calculate savings with dynamic tariff."""
    if not plz:
        plz = "all"

    # Get current exchange price from SMARD or DB
    try:
        prices = smard_client.get_latest_prices()
        if prices:
            avg_börse = sum(v for _, v in prices[-24:]) / 24 / 10.0  # ct/kWh
        else:
            avg_börse = 10.5  # fallback
    except Exception:
        avg_börse = 10.5

    # Calculate
    festpreis_total = verbrauch * FESTPREIS_AVG / 100
    dynamisch_total = verbrauch * (avg_börse + BÖRSEN_AUFSCHLAG) / 100
    ersparnis = festpreis_total - dynamisch_total

    # With optimization (shift 30% of load to cheapest hours = ~15% savings on that share)
    optimisation = ersparnis * 0.15
    ersparnis_optimiert = ersparnis + optimisation

    # Generate forecast snippet
    fc = forecast.forecast(hours=24)
    cheapest = min(fc, key=lambda x: x["price_ct"]) if fc else None

    result_html = f"""
    <div class="result-card">
        <div class="result-header">
            <span class="result-amount">€{ersparnis_optimiert:.0f}</span>
            <span class="result-label">Ersparnis pro Jahr*</span>
        </div>
        <div class="result-details">
            <div class="detail-row">
                <span>Festpreis ({FESTPREIS_AVG} ct/kWh)</span>
                <span>€{festpreis_total:.0f}/Jahr</span>
            </div>
            <div class="detail-row savings">
                <span>Dynamischer Tarif (ø {avg_börse:.1f} ct/kWh + Aufschlag)</span>
                <span>€{dynamisch_total:.0f}/Jahr</span>
            </div>
            <div class="detail-row">
                <span>Optimierung (30% Lastverschiebung)</span>
                <span>+€{optimisation:.0f}/Jahr</span>
            </div>
        </div>
        <div class="result-cta">
            <p class="result-disclaimer">*Berechnung basiert auf aktuellen Börsenstrompreisen. Individuelle Tarife variieren.</p>
            <a href="{AFFILIATE['tibber']}" class="cta-button" target="_blank" rel="sponsored">
                → Jetzt zu Tibber wechseln
            </a>
            <a href="{AFFILIATE['awattar']}" class="cta-button secondary" target="_blank" rel="sponsored">
                → Alternativ: Awattar
            </a>
        </div>
    </div>
    """

    # Add forecast snippet
    if cheapest:
        hour = cheapest["timestamp"][11:16]
        price = cheapest["price_ct"]
        result_html += f"""
        <div class="forecast-snippet">
            <p>⚡ Günstigste Stunde heute: <strong>{hour} Uhr</strong> (nur {price} ct/kWh)</p>
        </div>
        """

    return HTMLResponse(LANDING_HTML.replace(
        'id="result" class="result-placeholder"',
        f'id="result" class="result-active"'
    ).replace(
        "<!-- RESULT_WILL_BE_INSERTED_HERE -->",
        result_html
    ))


@app.get("/health")
async def health():
    """Health check for monitoring."""
    total = database.get_price_count()
    latest = database.get_latest_db_timestamp()
    return {
        "status": "ok",
        "db_rows": total,
        "db_latest": latest,
        "version": "0.2.0",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─── Landing Page HTML ────────────────────────────────────

LANDING_HTML = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stromcheck — Lohnt sich dynamischer Strom für dich?</title>
    <meta name="description" content="Berechne in 30 Sekunden, ob sich ein dynamischer Stromtarif für dich lohnt. Kostenlos, unverbindlich, datensicher.">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
            background: linear-gradient(135deg, #0c0e1a 0%, #1a1c2e 100%);
            color: #e0e0e0;
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .container { max-width: 640px; width: 100%; padding: 2rem 1.5rem; }
        header { text-align: center; margin-bottom: 2.5rem; }
        header h1 {
            font-size: 2rem;
            background: linear-gradient(135deg, #facc15, #f97316);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }
        header p { color: #9ca3af; font-size: 1.05rem; }
        .card {
            background: #1e2030;
            border: 1px solid #2d2f45;
            border-radius: 16px;
            padding: 2rem;
            margin-bottom: 1.5rem;
        }
        .form-group { margin-bottom: 1.5rem; }
        label {
            display: block;
            font-size: 0.9rem;
            font-weight: 600;
            color: #d1d5db;
            margin-bottom: 0.4rem;
        }
        input[type="number"], input[type="text"] {
            width: 100%;
            padding: 0.75rem 1rem;
            background: #252740;
            border: 1px solid #363857;
            border-radius: 10px;
            color: #e0e0e0;
            font-size: 1rem;
            transition: border 0.2s;
        }
        input:focus {
            outline: none;
            border-color: #facc15;
            box-shadow: 0 0 0 3px rgba(250,204,21,0.1);
        }
        .submit-btn {
            width: 100%;
            padding: 0.9rem;
            background: linear-gradient(135deg, #facc15, #f97316);
            color: #0c0e1a;
            border: none;
            border-radius: 10px;
            font-size: 1.1rem;
            font-weight: 700;
            cursor: pointer;
            transition: transform 0.15s, box-shadow 0.15s;
        }
        .submit-btn:hover {
            transform: translateY(-1px);
            box-shadow: 0 4px 20px rgba(250,204,21,0.25);
        }
        .result-card {
            background: linear-gradient(135deg, #1e2030, #252740);
            border: 1px solid #facc15;
            border-radius: 16px;
            padding: 2rem;
            margin-top: 1.5rem;
        }
        .result-header { text-align: center; margin-bottom: 1.5rem; }
        .result-amount {
            font-size: 3rem;
            font-weight: 800;
            background: linear-gradient(135deg, #facc15, #f97316);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: block;
        }
        .result-label { color: #9ca3af; font-size: 0.9rem; }
        .result-details { margin-bottom: 1.5rem; }
        .detail-row {
            display: flex;
            justify-content: space-between;
            padding: 0.6rem 0;
            border-bottom: 1px solid #2d2f45;
            font-size: 0.95rem;
        }
        .detail-row.savings { color: #4ade80; font-weight: 600; }
        .result-cta { text-align: center; }
        .result-disclaimer { color: #6b7280; font-size: 0.8rem; margin-bottom: 1rem; }
        .cta-button {
            display: block;
            padding: 0.9rem;
            background: linear-gradient(135deg, #facc15, #f97316);
            color: #0c0e1a;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 700;
            font-size: 1rem;
            margin-bottom: 0.75rem;
            transition: transform 0.15s;
        }
        .cta-button.secondary {
            background: #2d2f45;
            color: #e0e0e0;
        }
        .cta-button:hover { transform: translateY(-1px); }
        .forecast-snippet {
            background: #252740;
            border: 1px solid #2d2f45;
            border-radius: 12px;
            padding: 1rem 1.5rem;
            margin-top: 1rem;
            text-align: center;
            font-size: 0.95rem;
        }
        .forecast-snippet strong { color: #facc15; }
        .features {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 0.75rem;
            margin-bottom: 1.5rem;
        }
        .feature {
            background: #1e2030;
            border: 1px solid #2d2f45;
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
        }
        .feature-icon { font-size: 1.5rem; margin-bottom: 0.4rem; }
        .feature-text { font-size: 0.85rem; color: #9ca3af; }
        footer {
            text-align: center;
            color: #4b5563;
            font-size: 0.8rem;
            padding: 2rem 1rem;
        }
        footer a { color: #6b7280; }
        @media (max-width: 480px) { .features { grid-template-columns: 1fr; } }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ Lohnt sich dynamischer Strom?</h1>
            <p>Berechne in 30 Sekunden, ob sich ein Wechsel für dich lohnt.</p>
        </header>

        <div class="features">
            <div class="feature">
                <div class="feature-icon">📊</div>
                <div class="feature-text">Echte Börsenpreise</div>
            </div>
            <div class="feature">
                <div class="feature-icon">🔒</div>
                <div class="feature-text">Keine Speicherung</div>
            </div>
            <div class="feature">
                <div class="feature-icon">⚡</div>
                <div class="feature-text">24h-Prognose</div>
            </div>
        </div>

        <form class="card" method="post" action="/check">
            <div class="form-group">
                <label for="verbrauch">Jahresverbrauch (kWh)</label>
                <input type="number" id="verbrauch" name="verbrauch"
                       min="500" max="50000" value="3500" required>
                <small style="color:#6b7280;">Steht auf deiner letzten Stromrechnung</small>
            </div>
            <div class="form-group">
                <label for="plz">PLZ (optional)</label>
                <input type="text" id="plz" name="plz" maxlength="5"
                       placeholder="z.B. 69118">
            </div>
            <button type="submit" class="submit-btn">→ Berechnen</button>
        </form>

        <div id="result" class="result-placeholder">
            <!-- RESULT_WILL_BE_INSERTED_HERE -->
        </div>

        <footer>
            <p>Daten basieren auf SMARD (Bundesnetzagentur) live Börsenstrompreisen.</p>
            <p>Affiliate-Links zu Tibber und Awattar. <a href="/health">Status</a></p>
        </footer>
    </div>
</body>
</html>
"""
