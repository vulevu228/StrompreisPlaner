# Strompreis-Planer

**When is electricity cheapest today and tomorrow?** A free website with German day-ahead
electricity prices in 15-minute steps and a planner that finds the best time to run an EV,
washing machine, dishwasher, heat pump and more.

**Live:** https://strompreis-planer.de (German by default, English via the DE/EN switch)

## What it shows

- **Which tariff do you have?** The first card asks: fixed price (the default, as for most households)
  or dynamic tariff. Everything below follows that choice:
  - **Fixed price:** every hour costs the same, so the planner finds the **greenest** time; the tiles show
    the renewable share now and the greenest / least green hour; the chart shows what a dynamic tariff
    would cost, with your fixed price as a dashed line.
  - **Dynamic tariff:** the planner finds the **cheapest** time and your savings vs. starting now and vs.
    a fixed price; the tiles show the price now and the cheapest / most expensive hour.
- **15-minute price chart** for today and tomorrow, with the renewable-share forecast; tooltips show what
  you pay and what the other tariff would cost
- **Planner**: best start for fixed programmes (one continuous block) or the cheapest / greenest slots for
  pausable loads (EV, home battery)
- **Your tariff**: grid fees, taxes and levies, VAT and your fixed price, with hints where to find them on your bill
- **Heatmap** of the last 30 days: when electricity is usually cheap
- **Europe map**: hourly market prices of 17 neighbouring price zones, with a time slider
- Background cards: the daily price pattern, merit order, negative prices, dynamic tariffs, saving tips,
  safety, and a glossary of the harder terms (bidding zone, grid fees, concession fee, § 14a EnWG ...)

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
  Chart.js and the Inter font are served from `docs/vendor/`, so the page loads nothing from third parties.
- GitHub sometimes skips scheduled runs; a small watchdog on the maintainer's PC starts the workflow
  when tomorrow's prices are still missing in the afternoon.
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
- Bundled: [Chart.js](https://www.chartjs.org) 4.4.1 (MIT) and the [Inter](https://rsms.me/inter/) font
  (SIL Open Font License); licence texts in `docs/vendor/`

No cookies, no tracking: see the [privacy page](https://strompreis-planer.de/privacy.html).
All figures without guarantee; final prices are estimates based on the user's settings.
