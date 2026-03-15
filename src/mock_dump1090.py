"""
Mock dump1090 server - simulates ADS-B receiver for desktop development.
Run this to test the flight tracker without Pi hardware!

Usage:
  cd src
  python mock_dump1090.py

Improvements over the original:
  • Each aircraft carries pre-populated metadata (airline, route, aircraft type)
    so the data panel shows real content without waiting for OpenSky API calls.
  • photo_url is set to a deterministic picsum.photos URL seeded by the ICAO
    hex code, so every aircraft gets a consistent real photo at the correct
    300×168 pixel dimensions the UI expects.
  • baro_rate stays coherent with alt_baro (climbs slow down near cruise alt).
"""
from flask import Flask, jsonify
import random
import time

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Airline / route / aircraft type fixtures
# ---------------------------------------------------------------------------

AIRLINES = [
    {"iata": "AA",  "name": "American Airlines",  "callsign_prefix": "AAL"},
    {"iata": "UA",  "name": "United Airlines",     "callsign_prefix": "UAL"},
    {"iata": "DL",  "name": "Delta Air Lines",     "callsign_prefix": "DAL"},
    {"iata": "WN",  "name": "Southwest Airlines",  "callsign_prefix": "SWA"},
    {"iata": "AS",  "name": "Alaska Airlines",     "callsign_prefix": "ASA"},
    {"iata": "B6",  "name": "JetBlue Airways",     "callsign_prefix": "JBU"},
    {"iata": "F9",  "name": "Frontier Airlines",   "callsign_prefix": "FFT"},
    {"iata": "NK",  "name": "Spirit Airlines",     "callsign_prefix": "NKS"},
]

AIRCRAFT_TYPES = [
    {"code": "B738", "name": "Boeing 737-800"},
    {"code": "B739", "name": "Boeing 737-900"},
    {"code": "B77W", "name": "Boeing 777-300ER"},
    {"code": "B788", "name": "Boeing 787-8"},
    {"code": "A320", "name": "Airbus A320"},
    {"code": "A321", "name": "Airbus A321"},
    {"code": "B752", "name": "Boeing 757-200"},
    {"code": "E75L", "name": "Embraer E175"},
]

# Seattle-area routes (origin → destination pairs)
ROUTES = [
    ("SEA", "LAX"), ("SEA", "SFO"), ("SEA", "JFK"), ("SEA", "ORD"),
    ("SEA", "DEN"), ("SEA", "ATL"), ("SEA", "DFW"), ("SEA", "BOS"),
    ("SEA", "LAS"), ("SEA", "PHX"), ("LAX", "SEA"), ("SFO", "SEA"),
    ("JFK", "SEA"), ("ORD", "SEA"), ("DEN", "SEA"), ("ATL", "SEA"),
    ("SEA", "ANC"), ("SEA", "HNL"), ("SEA", "YVR"), ("PDX", "SEA"),
]

MOCK_AIRCRAFT: list = []


def _photo_url(hex_code: str) -> str:
    """
    Return a deterministic real photo URL for a given ICAO hex.

    picsum.photos/seed/<seed>/w/h returns a consistent real photograph
    every time for the same seed — perfect for dev/test without real
    Planespotters data.  The seed is the hex code so each aircraft always
    gets the same image across restarts.
    """
    return f"https://picsum.photos/seed/{hex_code}/300/168"


def generate_aircraft() -> dict:
    """Generate one realistic Seattle-area aircraft with full metadata."""
    airline     = random.choice(AIRLINES)
    ac_type     = random.choice(AIRCRAFT_TYPES)
    route       = random.choice(ROUTES)
    hex_code    = f"{random.randint(0, 0xFFFFFF):06x}"
    flight_num  = f"{airline['callsign_prefix']}{random.randint(100, 9999)}"
    alt         = random.randint(8000, 38000)

    # Vertical rate biased toward level cruise; departures climb, arrivals descend
    bias = random.choice(["climb", "level", "level", "level", "descend"])
    if bias == "climb":
        baro_rate = random.randint(500, 2500)
    elif bias == "descend":
        baro_rate = random.randint(-2500, -500)
    else:
        baro_rate = random.randint(-200, 200)

    return {
        # ADS-B / dump1090 standard fields
        "hex":       hex_code,
        "flight":    f"{flight_num:<8}",        # dump1090 pads to 8 chars
        "lat":       47.6062 + random.uniform(-0.8, 0.8),
        "lon":       -122.3321 + random.uniform(-0.8, 0.8),
        "alt_baro":  alt,
        "gs":        random.uniform(280, 520),
        "track":     random.randint(0, 359),
        "baro_rate": baro_rate,
        "squawk":    f"{random.randint(1000, 7777):04d}",
        "category":  "A3",
        "messages":  random.randint(100, 1000),
        "seen":      round(random.uniform(0.1, 2.0), 1),

        # Pre-populated metadata (skips OpenSky API during dev)
        "origin":        route[0],
        "destination":   route[1],
        "airline":       airline["name"],
        "aircraft_type": ac_type["code"],
        "model":         ac_type["name"],
        "registration":  f"N{random.randint(100, 999)}{random.choice('ABCDEFGHJKLMNPQRSTUVWXYZ')}",

        # Real photo via picsum.photos (deterministic per hex)
        "photo_url": _photo_url(hex_code),
    }


# Seed the initial traffic (5–8 aircraft)
for _ in range(random.randint(5, 8)):
    MOCK_AIRCRAFT.append(generate_aircraft())


# ---------------------------------------------------------------------------
# Flask routes
# ---------------------------------------------------------------------------

@app.route("/data/aircraft.json")
def get_aircraft():
    """Simulates the dump1090-fa /data/aircraft.json endpoint."""

    # 8 % chance a new aircraft enters range each poll
    if random.random() < 0.08 and len(MOCK_AIRCRAFT) < 25:
        new_ac = generate_aircraft()
        MOCK_AIRCRAFT.append(new_ac)
        print(f"[+] New: {new_ac['flight'].strip():8s}  "
              f"{new_ac['origin']}→{new_ac['destination']}  "
              f"{new_ac['alt_baro']:,} ft")

    # Update positions and motion
    for ac in MOCK_AIRCRAFT:
        ac["lat"]      += random.uniform(-0.008, 0.008)
        ac["lon"]      += random.uniform(-0.008, 0.008)
        ac["alt_baro"]  = max(500, ac["alt_baro"] + ac["baro_rate"] // 30)
        # Nudge baro_rate toward level over time (simulate cruise)
        ac["baro_rate"] = int(ac["baro_rate"] * 0.95 + random.randint(-50, 50))
        ac["messages"] += random.randint(1, 5)
        ac["seen"]      = round(random.uniform(0.1, 2.0), 1)

    # 4 % chance an aircraft leaves range
    if len(MOCK_AIRCRAFT) > 4 and random.random() < 0.04:
        removed = MOCK_AIRCRAFT.pop(random.randint(0, len(MOCK_AIRCRAFT) - 1))
        print(f"[-] Left:  {removed['flight'].strip()}")

    return jsonify({
        "aircraft": MOCK_AIRCRAFT,
        "now":      time.time(),
        "messages": sum(ac["messages"] for ac in MOCK_AIRCRAFT),
    })


@app.route("/")
def index():
    return (
        "<h2>Mock dump1090</h2>"
        f"<p>Tracking {len(MOCK_AIRCRAFT)} aircraft near Seattle.</p>"
        "<p><a href='/data/aircraft.json'>View JSON</a></p>"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("  Mock dump1090 — Flight Tracker Development Server")
    print("=" * 60)
    print(f"  Simulating {len(MOCK_AIRCRAFT)} aircraft near Seattle")
    print(f"  API:    http://localhost:8080/data/aircraft.json")
    print(f"  Photos: real images via picsum.photos (no API key needed)")
    print()
    print("  Press CTRL+C to stop")
    print("=" * 60)
    app.run(port=8080, debug=False, host="127.0.0.1")
