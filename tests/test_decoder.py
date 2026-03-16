"""
Tests for decoder.py — JSON parsing, distance/bearing math, get_aircraft().
"""
from unittest.mock import MagicMock, patch

import pytest

import decoder

HOME_LAT = 47.6541
HOME_LON = -122.35

# ---------------------------------------------------------------------------
# haversine_miles
# ---------------------------------------------------------------------------

def test_haversine_same_point():
    assert decoder.haversine_miles(47.0, -122.0, 47.0, -122.0) == pytest.approx(0.0, abs=0.01)


def test_haversine_known_distance():
    # Seattle to Portland is roughly 145–150 miles
    dist = decoder.haversine_miles(47.6541, -122.35, 45.5231, -122.6765)
    assert 140 < dist < 155


def test_haversine_symmetry():
    d1 = decoder.haversine_miles(47.0, -122.0, 48.0, -121.0)
    d2 = decoder.haversine_miles(48.0, -121.0, 47.0, -122.0)
    assert d1 == pytest.approx(d2, rel=1e-6)


def test_haversine_positive():
    dist = decoder.haversine_miles(47.0, -122.0, 48.0, -121.0)
    assert dist > 0


# ---------------------------------------------------------------------------
# bearing_degrees
# ---------------------------------------------------------------------------

def test_bearing_due_north():
    b = decoder.bearing_degrees(47.0, -122.0, 48.0, -122.0)
    assert b == pytest.approx(0.0, abs=1.0)


def test_bearing_due_east():
    b = decoder.bearing_degrees(47.0, -122.0, 47.0, -121.0)
    assert b == pytest.approx(90.0, abs=1.0)


def test_bearing_due_south():
    b = decoder.bearing_degrees(48.0, -122.0, 47.0, -122.0)
    assert b == pytest.approx(180.0, abs=1.0)


def test_bearing_due_west():
    b = decoder.bearing_degrees(47.0, -121.0, 47.0, -122.0)
    assert b == pytest.approx(270.0, abs=1.0)


def test_bearing_always_in_range():
    for dlat, dlon in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        b = decoder.bearing_degrees(47.0, -122.0, 47.0 + dlat, -122.0 + dlon)
        assert 0 <= b < 360


# ---------------------------------------------------------------------------
# parse_aircraft
# ---------------------------------------------------------------------------

BASIC_RAW = {
    "hex": "a1b2c3",
    "flight": "UAL123  ",
    "lat": 47.9,
    "lon": -122.1,
    "alt_baro": 35000,
    "gs": 450,
    "track": 90,
    "baro_rate": 0,
}


def test_parse_basic_fields():
    ac = decoder.parse_aircraft(BASIC_RAW, HOME_LAT, HOME_LON)
    assert ac is not None
    assert ac["icao_hex"] == "a1b2c3"
    assert ac["callsign"] == "UAL123"
    assert ac["altitude"] == 35000
    assert ac["speed"] == 450
    assert ac["track"] == 90
    assert ac["vert_trend"] == "level"


def test_parse_missing_lat_returns_none():
    raw = {k: v for k, v in BASIC_RAW.items() if k != "lat"}
    assert decoder.parse_aircraft(raw, HOME_LAT, HOME_LON) is None


def test_parse_missing_lon_returns_none():
    raw = {k: v for k, v in BASIC_RAW.items() if k != "lon"}
    assert decoder.parse_aircraft(raw, HOME_LAT, HOME_LON) is None


def test_parse_ground_altitude_string():
    raw = {**BASIC_RAW, "alt_baro": "ground"}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["altitude"] == 0


def test_parse_climbing():
    raw = {**BASIC_RAW, "baro_rate": 1500}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["vert_trend"] == "climbing"


def test_parse_descending():
    raw = {**BASIC_RAW, "baro_rate": -1500}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["vert_trend"] == "descending"


def test_parse_level_at_boundaries():
    for rate in (0, 200, -200):
        raw = {**BASIC_RAW, "baro_rate": rate}
        ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
        assert ac["vert_trend"] == "level", f"rate={rate} should be level"


def test_parse_empty_callsign_is_none():
    raw = {**BASIC_RAW, "flight": "   "}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["callsign"] is None


def test_parse_missing_callsign_is_none():
    raw = {k: v for k, v in BASIC_RAW.items() if k != "flight"}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["callsign"] is None


def test_parse_icao_lowercased_and_stripped():
    raw = {**BASIC_RAW, "hex": "  A1B2C3  "}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["icao_hex"] == "a1b2c3"


def test_parse_distance_positive():
    ac = decoder.parse_aircraft(BASIC_RAW, HOME_LAT, HOME_LON)
    assert ac["distance"] > 0


def test_parse_bearing_in_range():
    ac = decoder.parse_aircraft(BASIC_RAW, HOME_LAT, HOME_LON)
    assert 0 <= ac["bearing"] < 360


def test_parse_optional_hardware_fields_none_when_absent():
    ac = decoder.parse_aircraft(BASIC_RAW, HOME_LAT, HOME_LON)
    assert ac["rssi"] is None
    assert ac["tas"] is None
    assert ac["ias"] is None
    assert ac["mach"] is None
    assert ac["squawk"] is None
    assert ac["nav_heading"] is None


def test_parse_alt_geom_string_becomes_none():
    raw = {**BASIC_RAW, "alt_geom": "ground"}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["alt_geom"] is None


def test_parse_passthrough_fields():
    raw = {**BASIC_RAW, "origin": "SEA", "destination": "LAX", "registration": "N12345"}
    ac = decoder.parse_aircraft(raw, HOME_LAT, HOME_LON)
    assert ac["origin"] == "SEA"
    assert ac["destination"] == "LAX"
    assert ac["registration"] == "N12345"


# ---------------------------------------------------------------------------
# get_aircraft
# ---------------------------------------------------------------------------

def test_get_aircraft_returns_empty_on_connection_error():
    with patch("decoder.requests.get", side_effect=ConnectionError("refused")):
        result = decoder.get_aircraft("http://localhost:9999")
    assert result == []


def test_get_aircraft_returns_empty_on_timeout():
    with patch("decoder.requests.get", side_effect=TimeoutError()):
        result = decoder.get_aircraft("http://localhost:9999")
    assert result == []


def test_get_aircraft_parses_aircraft_list():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"aircraft": [BASIC_RAW, BASIC_RAW]}
    with patch("decoder.requests.get", return_value=mock_resp):
        result = decoder.get_aircraft("http://localhost:8080")
    assert len(result) == 2


def test_get_aircraft_missing_key_returns_empty():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}   # no "aircraft" key
    with patch("decoder.requests.get", return_value=mock_resp):
        result = decoder.get_aircraft("http://localhost:8080")
    assert result == []


def test_get_aircraft_uses_correct_url():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"aircraft": []}
    with patch("decoder.requests.get", return_value=mock_resp) as mock_get:
        decoder.get_aircraft("http://myserver:8080")
    mock_get.assert_called_once()
    called_url = mock_get.call_args[0][0]
    assert called_url == "http://myserver:8080/data/aircraft.json"
