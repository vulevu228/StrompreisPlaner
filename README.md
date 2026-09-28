# Strompreis-Planer

**When is electricity cheapest today and tomorrow?** A free website with German day-ahead
electricity prices in 15-minute steps and a planner that finds the best time to run an EV,
washing machine, dishwasher, heat pump and more.

**Live:** https://strompreis-planer.de (German by default, English via the DE/EN switch)

## What it shows

- **Price now, cheapest and most expensive hour**, and how tomorrow compares with the last 30 days
- **15-minute price chart** for today and tomorrow, with the renewable-share forecast
- **Planner**: best start for fixed programmes (one continuous block) or the cheapest slots for
  pausable loads (EV, home battery), cost vs. "start now" vs. a fixed tariff, plus the greenest time
- **Your tariff**: turns the market price into your final price (grid fees, taxes, levies, VAT)
- **Heatmap** of the last 30 days: when electricity is usually cheap
- **Europe map**: hourly market prices of 17 neighbouring price zones, with a time slider
- Background cards: the daily price pattern, merit order, negative prices, dynamic tariffs, saving tips

## How it works

```
energy-charts.info API ──> scripts/fetch_prices.py ──> docs/data/*.json ──> docs/index.html
        (GitHub Actions, several times a day)            (static files)     (all maths in the browser)
```

- `scripts/fetch_prices.py` fetches day-ahead prices for DE-LU and the renewable-share forecast,
  keeps a growing history in `data/prices_15min.csv`, and writes `docs/data/latest.json` (~10 KB).
  It also writes `docs/data/europe.json` with hourly prices of neighbouring zones (skipped once
  today and tomorrow are complete, because day-ahead prices never change).
- `.github/workflows/fetch-prices.yml` runs the script several times a day (tomorrow's prices are
  published around 13:00 German time) and commits only when the data changed.
- `docs/index.html` is a single static page (Chart.js, no build step). Visitors never call the API.
- `scripts/build_map.py` is a one-time build of the Europe map outline from Natural Earth
  (`docs/data/europe-map.json`); it needs `shapely`, which the workflow does not.

## Run locally

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows; use .venv/bin/pip elsewhere
.venv/Scripts/python scripts/fetch_prices.py
cd docs && python -m http.server 8000             # open http://localhost:8000
```

## Data and licence

- Prices: Bundesnetzagentur | SMARD.de via [energy-charts.info](https://energy-charts.info)
  (Fraunhofer ISE), CC BY 4.0
- Map outlines: [Natural Earth](https://www.naturalearthdata.com), public domain

All figures without guarantee; final prices are estimates based on the user's settings.
