"""
Fetches German day-ahead electricity prices (15-minute slots, bidding zone
DE-LU) and the renewable-share forecast from the energy-charts.info API
(Fraunhofer ISE; prices from Bundesnetzagentur | SMARD.de, CC BY 4.0).

Writes:
  data/prices_15min.csv    growing price history (unix_seconds, eur_mwh)
  docs/data/latest.json    everything the website needs, in one small file
  docs/data/europe.json    hourly prices of neighbouring countries for the map

The API allows no browser access from other sites and rate-limits quickly,
so visitors never call it: this script runs a few times a day in GitHub
Actions and the website only reads latest.json.

Run:  python scripts/fetch_prices.py
"""

import csv
import json
import statistics
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

API = "https://api.energy-charts.info"
BERLIN = ZoneInfo("Europe/Berlin")
ROOT = Path(__file__).resolve().parent.parent
HISTORY_CSV = ROOT / "data" / "prices_15min.csv"
LATEST_JSON = ROOT / "docs" / "data" / "latest.json"
FIRST_RUN_DAYS = 60     # history pulled on the very first run
CONTEXT_DAYS = 30       # days of history shipped to the website


def get(endpoint: str, **params) -> dict:
    """GET with retries; energy-charts answers 429 when called too often."""
    for attempt in range(5):
        try:
            resp = requests.get(f"{API}/{endpoint}", params=params, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            if attempt == 4:
                raise
            wait = 15 * (attempt + 1)
            print(f"  {endpoint}: {exc}, retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)


def fetch_prices(start: date, end: date) -> dict[int, float]:
    """Prices from start (inclusive) to end (exclusive), as {unix_seconds: EUR/MWh}."""
    j = get("price", bzn="DE-LU", start=start.isoformat(), end=end.isoformat())
    return {int(t): float(p) for t, p in zip(j["unix_seconds"], j["price"]) if p is not None}


def fetch_green() -> dict[int, tuple[float, int]]:
    """Renewable share forecast (%) and the 'Stromampel' signal for today and tomorrow."""
    j = get("signal", country="de")
    return {int(t): (s, sig) for t, s, sig in zip(j["unix_seconds"], j["share"], j["signal"]) if s is not None}


def load_history() -> dict[int, float]:
    if not HISTORY_CSV.exists():
        return {}
    with HISTORY_CSV.open(newline="") as f:
        return {int(r["unix_seconds"]): float(r["eur_mwh"]) for r in csv.DictReader(f)}


def save_history(prices: dict[int, float]) -> None:
    HISTORY_CSV.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY_CSV.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["unix_seconds", "eur_mwh"])
        w.writerows(sorted(prices.items()))


def local_day(ts: int) -> date:
    return datetime.fromtimestamp(ts, BERLIN).date()


def daily_summary(prices: dict[int, float], days: list[date]) -> list[dict]:
    """Per day: mean/min/max and 24 hourly means (for the heatmap and 'how cheap is tomorrow')."""
    by_day: dict[date, list[tuple[int, float]]] = {}
    for ts, p in prices.items():
        by_day.setdefault(local_day(ts), []).append((ts, p))
    out = []
    for d in days:
        slots = sorted(by_day.get(d, []))
        if len(slots) < 80:  # incomplete day (a DST day has 92 or 100 slots)
            continue
        hourly: dict[int, list[float]] = {}
        for ts, p in slots:
            hourly.setdefault(datetime.fromtimestamp(ts, BERLIN).hour, []).append(p)
        values = [p for _, p in slots]
        out.append({
            "date": d.isoformat(),
            "mean": round(statistics.mean(values), 2),
            "min": min(values),
            "max": max(values),
            "hourly": [round(statistics.mean(hourly[h]), 2) if h in hourly else None for h in range(24)],
        })
    return out


# Neighbouring bidding zones for the Europe map: zone -> map countries (Natural Earth ADM0_A3).
# Countries split into several zones are shown with the zone nearest to Germany.
EUROPE_ZONES = {
    "DE-LU": ["DEU", "LUX"], "FR": ["FRA"], "NL": ["NLD"], "BE": ["BEL"], "AT": ["AUT"], "CH": ["CHE"],
    "PL": ["POL"], "CZ": ["CZE"], "DK1": ["DNK"], "SE4": ["SWE"], "NO2": ["NOR"], "IT-North": ["ITA"],
    "SK": ["SVK"], "HU": ["HUN"], "SI": ["SVN"], "ES": ["ESP"], "PT": ["PRT"],
}
EUROPE_JSON = ROOT / "docs" / "data" / "europe.json"
EUROPE_PAUSE = 12  # seconds between calls; the API allows only a few per minute


def hourly_by_day(prices: dict[int, float], days: list[date]) -> dict[str, list]:
    """{day: 24 hourly means in Berlin local time} for the days that are (almost) complete."""
    buckets: dict[date, dict[int, list[float]]] = {}
    for ts, p in prices.items():
        dt = datetime.fromtimestamp(ts, BERLIN)
        buckets.setdefault(dt.date(), {}).setdefault(dt.hour, []).append(p)
    out = {}
    for d in days:
        hours = buckets.get(d, {})
        if len(hours) >= 23:  # a DST day has 23 hours
            out[d.isoformat()] = [round(statistics.mean(hours[h]), 2) if h in hours else None for h in range(24)]
    return out


def update_europe(today: date) -> None:
    """Hourly day-ahead prices of Germany's neighbours for today and tomorrow -> docs/data/europe.json.
    Skipped when the file already holds complete data for both days (prices never change once set)."""
    tomorrow = today + timedelta(days=1)
    days = [today, tomorrow]
    try:
        old = json.loads(EUROPE_JSON.read_text(encoding="utf-8"))
        if old.get("days") == [d.isoformat() for d in days] and all(
                len(z["hourly"]) == 2 for z in old["zones"].values()) and len(old["zones"]) == len(EUROPE_ZONES):
            print("europe.json already complete for today and tomorrow")
            return
    except (FileNotFoundError, ValueError, KeyError):
        old = None
    zones = {}
    for i, (zone, countries) in enumerate(EUROPE_ZONES.items()):
        if i:
            time.sleep(EUROPE_PAUSE)
        try:
            j = get("price", bzn=zone, start=today.isoformat(), end=(today + timedelta(days=2)).isoformat())
        except requests.RequestException as exc:
            print(f"  {zone}: skipped ({exc})", file=sys.stderr)
            # keep what we had for this zone rather than dropping it from the map
            if old and zone in old.get("zones", {}):
                kept = {d: v for d, v in old["zones"][zone]["hourly"].items() if d in {x.isoformat() for x in days}}
                if kept:
                    zones[zone] = {"countries": countries, "hourly": kept}
            continue
        prices = {int(t): float(p) for t, p in zip(j["unix_seconds"], j["price"]) if p is not None}
        hourly = hourly_by_day(prices, days)
        if hourly:
            zones[zone] = {"countries": countries, "hourly": hourly}
    europe = {
        "unit": "EUR/MWh", "timezone": "Europe/Berlin",
        "days": [d.isoformat() for d in days],
        "zones": zones,
        "source": "ENTSO-E / Bundesnetzagentur | SMARD.de via energy-charts.info (Fraunhofer ISE), CC BY 4.0",
    }
    if old and {k: v for k, v in old.items() if k != "generated"} == europe:
        print("europe.json unchanged")
        return
    europe["generated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    EUROPE_JSON.write_text(json.dumps(europe, separators=(",", ":")), encoding="utf-8")
    print(f"europe.json: {len(zones)}/{len(EUROPE_ZONES)} zones, {EUROPE_JSON.stat().st_size / 1024:.0f} KB")


def main() -> None:
    update_germany()
    # the map is a nice extra: never let it fail the run
    try:
        time.sleep(EUROPE_PAUSE)
        update_europe(datetime.now(BERLIN).date())
    except Exception as exc:
        print(f"europe map data not updated: {exc}", file=sys.stderr)


def update_germany() -> None:
    today = datetime.now(BERLIN).date()
    history = load_history()

    # Re-fetch from the last stored day (it may have been partial) through tomorrow
    start = local_day(max(history)) if history else today - timedelta(days=FIRST_RUN_DAYS)
    fresh = fetch_prices(start, today + timedelta(days=2))
    history.update(fresh)
    save_history(history)
    print(f"prices: {len(fresh)} slots fetched from {start}, history now {len(history)} slots")

    try:
        green = fetch_green()
    except requests.RequestException as exc:  # prices matter most; ship without green data
        print(f"green share unavailable: {exc}", file=sys.stderr)
        green = {}

    window_start = int(datetime.combine(today, datetime.min.time(), BERLIN).timestamp())
    slots = [[ts, p, *green.get(ts, (None, None))] for ts, p in sorted(history.items()) if ts >= window_start]
    tomorrow = today + timedelta(days=1)
    tomorrow_slots = sum(1 for s in slots if local_day(s[0]) == tomorrow)
    context_days = [today - timedelta(days=i) for i in range(CONTEXT_DAYS, 0, -1)]

    latest = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timezone": "Europe/Berlin",
        "unit": "EUR/MWh",
        "slot_minutes": 15,
        "tomorrow_available": tomorrow_slots >= 80,
        "columns": ["unix_seconds", "eur_mwh", "renewable_share_pct", "signal"],
        "slots": slots,
        "history": daily_summary(history, context_days),
        "source": "Bundesnetzagentur | SMARD.de via energy-charts.info (Fraunhofer ISE), CC BY 4.0",
    }
    # Only rewrite when the data changed, so runs without news don't create commits
    try:
        old = json.loads(LATEST_JSON.read_text(encoding="utf-8"))
        if {k: v for k, v in old.items() if k != "generated"} == {k: v for k, v in latest.items() if k != "generated"}:
            print("latest.json unchanged")
            return
    except (FileNotFoundError, ValueError):
        pass
    LATEST_JSON.parent.mkdir(parents=True, exist_ok=True)
    LATEST_JSON.write_text(json.dumps(latest, separators=(",", ":")), encoding="utf-8")
    print(f"latest.json: {len(slots)} slots from today, tomorrow available: {latest['tomorrow_available']}, "
          f"{len(latest['history'])} history days, {LATEST_JSON.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
