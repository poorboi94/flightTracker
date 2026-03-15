"""
External API client for flight metadata and aircraft photos.

APIs used:
  - OpenSky Network  — flight routes and aircraft metadata (free, no key needed)
  - Planespotters    — aircraft photos (free, no key needed)

All results are cached to disk for 24 hours to stay within free-tier rate
limits and keep the UI fast on subsequent lookups.

Cache directory: <project root>/cache/
"""
import hashlib
import os
import time
import json
import requests

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "cache",
)
CACHE_TTL = 86400   # 24 hours in seconds

os.makedirs(CACHE_DIR, exist_ok=True)

HEADERS = {"User-Agent": "PersonalFlightTracker/1.0 (non-commercial)"}


def _cache_path(key, binary=False):
    safe = key.replace("/", "_").replace(":", "_").replace("?", "_").replace("&", "_")
    ext = ".bin" if binary else ".json"
    return os.path.join(CACHE_DIR, safe + ext)


def _cache_get(key):
    """Return cached data dict or None if missing/expired."""
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            entry = json.load(f)
        if time.time() - entry.get("ts", 0) < CACHE_TTL:
            return entry.get("data")
    except Exception:
        pass
    return None


def _cache_set(key, data):
    path = _cache_path(key)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "data": data}, f)
    except Exception:
        pass


def _cache_get_binary(key):
    path = _cache_path(key, binary=True)
    meta_path = path + ".meta.json"
    if not os.path.exists(path) or not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r") as f:
            meta = json.load(f)
        if time.time() - meta.get("ts", 0) < CACHE_TTL:
            with open(path, "rb") as f:
                return f.read()
    except Exception:
        pass
    return None


def _cache_set_binary(key, data):
    path = _cache_path(key, binary=True)
    meta_path = path + ".meta.json"
    try:
        with open(path, "wb") as f:
            f.write(data)
        with open(meta_path, "w") as f:
            json.dump({"ts": time.time()}, f)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# OpenSky Network — route and aircraft metadata
# ---------------------------------------------------------------------------

def get_flight_info(callsign, icao_hex):
    """
    Look up route and aircraft metadata via OpenSky Network.

    Returns a dict with any subset of:
        origin, destination, airline,
        aircraft_type, registration, manufacturer, model

    All values may be empty strings if the API doesn't know them.
    Returns {} on complete failure.
    """
    if not callsign and not icao_hex:
        return {}

    cache_key = f"flightinfo_{callsign or ''}_{icao_hex or ''}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    result = {}

    # --- Route lookup (needs callsign) ---
    if callsign:
        try:
            resp = requests.get(
                f"https://api.adsbdb.com/v0/callsign/{callsign}",
                headers=HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                body = resp.json().get("response", {})
                if body == "unknown callsign":
                    # Definitive miss — cache it so we don't retry
                    result["route_unknown"] = True
                else:
                    fr     = body.get("flightroute", {})
                    origin = fr.get("origin", {})
                    dest   = fr.get("destination", {})
                    if origin.get("iata_code"):
                        result["origin"] = origin["iata_code"]
                    if dest.get("iata_code"):
                        result["destination"] = dest["iata_code"]
                    airline = fr.get("airline", {})
                    if airline.get("name"):
                        result["airline"] = airline["name"]
        except Exception:
            pass

    # --- Aircraft metadata (needs ICAO hex) ---
    if icao_hex:
        try:
            resp = requests.get(
                f"https://opensky-network.org/api/metadata/aircraft/icao/{icao_hex.upper()}",
                headers=HEADERS,
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                result.setdefault("aircraft_type",  data.get("typecode", ""))
                result.setdefault("registration",   data.get("registration", ""))
                result.setdefault("manufacturer",   data.get("manufacturerName", ""))
                result.setdefault("model",          data.get("model", ""))
                # Use operator from metadata only if route lookup didn't find one
                if not result.get("airline"):
                    result["airline"] = (
                        data.get("operatorIata") or data.get("owner", "")
                    )
        except Exception:
            pass

    _cache_set(cache_key, result)
    return result


# ---------------------------------------------------------------------------
# Planespotters — aircraft photos
# ---------------------------------------------------------------------------

def get_aircraft_photo_url(icao_hex):
    """
    Return the best available photo URL for an aircraft, or None.

    Tries to get a large thumbnail first, falls back to small thumbnail.
    Result is cached for 24 hours.
    """
    if not icao_hex:
        return None

    cache_key = f"photourl_{icao_hex.lower()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached.get("url")   # may legitimately be None (no photo exists)

    url = None
    try:
        resp = requests.get(
            f"https://api.planespotters.net/pub/photos/hex/{icao_hex.upper()}",
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                photo = photos[0]
                url = (
                    photo.get("thumbnail_large", {}).get("src")
                    or photo.get("thumbnail", {}).get("src")
                )
    except Exception:
        pass

    _cache_set(cache_key, {"url": url})
    return url


# ---------------------------------------------------------------------------
# Nominatim — address geocoding (free, no key)
# ---------------------------------------------------------------------------

def geocode_address(address: str) -> "tuple[float, float, str] | None":
    """
    Convert a human-readable address to (lat, lon, display_name) using
    OpenStreetMap's Nominatim service.

    Returns (lat, lon, display_name) or None on failure.
    Results are cached for 24 hours.
    """
    if not address.strip():
        return None

    cache_key = f"geocode_{hashlib.md5(address.lower().encode()).hexdigest()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        if cached:
            return cached["lat"], cached["lon"], cached["display_name"]
        return None

    try:
        resp = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": address, "format": "json", "limit": 1},
            headers=HEADERS,
            timeout=10,
        )
        if resp.status_code == 200:
            results = resp.json()
            if results:
                r = results[0]
                lat  = float(r["lat"])
                lon  = float(r["lon"])
                name = r.get("display_name", address)
                _cache_set(cache_key, {"lat": lat, "lon": lon, "display_name": name})
                return lat, lon, name
    except Exception:
        pass

    _cache_set(cache_key, {})   # cache the miss so we don't hammer the API
    return None


def fetch_photo_bytes(url):
    """
    Download raw photo bytes from a URL.
    Results are cached to disk so the image is only downloaded once.
    Returns bytes or None.
    """
    if not url:
        return None

    cache_key = f"photoimg_{hashlib.md5(url.encode()).hexdigest()}"
    cached = _cache_get_binary(cache_key)
    if cached is not None:
        return cached

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            _cache_set_binary(cache_key, resp.content)
            return resp.content
        print(f"[api] Photo HTTP {resp.status_code} for {url}", flush=True)
    except Exception as e:
        print(f"[api] Photo request failed for {url}: {e}", flush=True)

    return None
