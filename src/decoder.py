"""
ADS-B decoder - polls the dump1090 JSON endpoint and parses aircraft data.

Works with both:
  - Real dump1090-fa on the Pi (http://localhost:8080/data/aircraft.json)
  - Mock server (mock_dump1090.py) for desktop development

Real dump1090-fa provides extra fields (rssi, nav_heading, tas, ias, etc.)
which are captured here when present. All fields are optional so the decoder
works identically against the mock server.
"""
import math
import time
import requests


def get_aircraft(dump1090_url):
    """Fetch raw aircraft list from dump1090. Returns [] on any failure."""
    try:
        resp = requests.get(f"{dump1090_url}/data/aircraft.json", timeout=2)
        resp.raise_for_status()
        return resp.json().get("aircraft", [])
    except Exception:
        return []


def haversine_miles(lat1, lon1, lat2, lon2):
    """Great-circle distance in miles between two lat/lon points."""
    R = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def bearing_degrees(lat1, lon1, lat2, lon2):
    """Compass bearing (0–360°) from home to aircraft."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2)
         - math.sin(phi1) * math.cos(phi2) * math.cos(dlambda))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def parse_aircraft(raw, home_lat, home_lon):
    """
    Convert a raw dump1090 aircraft dict into a cleaned record.

    Returns None when the aircraft has no position data yet (common early in
    a flight's reception — dump1090 may receive speed/altitude messages before
    it has decoded a position).

    Fields present on the real dump1090-fa but absent in the mock are captured
    when available and stored as None otherwise, so callers can always rely on
    the same dict shape.
    """
    lat = raw.get("lat")
    lon = raw.get("lon")
    if lat is None or lon is None:
        return None

    # altitude: dump1090 sends the string "ground" when the aircraft is on
    # the ground rather than an integer
    alt_baro = raw.get("alt_baro", 0)
    if isinstance(alt_baro, str):
        alt_baro = 0
    alt_geom = raw.get("alt_geom")          # geometric (GPS) altitude, ft
    if isinstance(alt_geom, str):
        alt_geom = None

    baro_rate = raw.get("baro_rate") or 0
    if baro_rate > 200:
        vert_trend = "climbing"
    elif baro_rate < -200:
        vert_trend = "descending"
    else:
        vert_trend = "level"

    distance = haversine_miles(home_lat, home_lon, lat, lon)
    bearing  = bearing_degrees(home_lat, home_lon, lat, lon)

    # Signal quality — only available from real hardware
    rssi = raw.get("rssi")          # dBFS, e.g. -15.2

    # Navigation state — real dump1090-fa only
    nav_heading  = raw.get("nav_heading")   # selected heading, degrees
    nav_altitude = raw.get("nav_altitude_mcp")  # autopilot target altitude, ft
    nav_modes    = raw.get("nav_modes", [])     # list: "autopilot", "vnav", etc.

    # Airspeed variants — real dump1090-fa only
    tas  = raw.get("tas")   # true airspeed, knots
    ias  = raw.get("ias")   # indicated airspeed, knots
    mach = raw.get("mach")  # mach number

    # Other real-hardware extras
    roll         = raw.get("roll")          # roll angle, degrees
    track_rate   = raw.get("track_rate")    # track rate of change, deg/s
    seen_pos     = raw.get("seen_pos")      # seconds since last position msg
    messages     = raw.get("messages", 0)   # total ADS-B messages received
    seen         = raw.get("seen", 0)       # seconds since any message

    return {
        # Core identity
        "icao_hex":     raw.get("hex", "").lower().strip(),
        "callsign":     raw.get("flight", "").strip() or None,

        # Position
        "lat":          lat,
        "lon":          lon,
        "altitude":     int(alt_baro),
        "alt_geom":     int(alt_geom) if alt_geom is not None else None,

        # Motion
        "speed":        round(raw.get("gs") or 0),     # ground speed, knots
        "track":        raw.get("track") or 0,          # true track, degrees
        "baro_rate":    int(baro_rate),                 # vertical rate, fpm
        "vert_trend":   vert_trend,                     # "climbing"/"descending"/"level"
        "roll":         roll,
        "track_rate":   track_rate,

        # Airspeed (real hardware only)
        "tas":          tas,
        "ias":          ias,
        "mach":         mach,

        # Transponder
        "squawk":       raw.get("squawk"),
        "category":     raw.get("category"),            # e.g. "A3"

        # Navigation state (real hardware only)
        "nav_heading":  nav_heading,
        "nav_altitude": nav_altitude,
        "nav_modes":    nav_modes,

        # Signal quality (real hardware only)
        "rssi":         rssi,

        # Relative to home
        "distance":     round(distance, 1),             # miles
        "bearing":      round(bearing, 1),              # degrees

        # Timing
        "last_seen":    time.time(),
        "messages":     messages,
        "seen":         seen,
        "seen_pos":     seen_pos,

        # Pass-through fields injected by the mock server (ignored on real hardware).
        # COALESCE in the DB upsert means these only take effect when not already set.
        "origin":        raw.get("origin"),
        "destination":   raw.get("destination"),
        "airline":       raw.get("airline"),
        "aircraft_type": raw.get("aircraft_type"),
        "model":         raw.get("model"),
        "registration":  raw.get("registration"),
        "photo_url":     raw.get("photo_url"),
    }
