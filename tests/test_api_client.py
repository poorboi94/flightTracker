"""
Tests for api_client.py — cache helpers, photo URL, geolocation, flight info.
All network calls are mocked; no real HTTP requests are made.
"""
import hashlib
import time
from unittest.mock import MagicMock, patch

import pytest

import api_client


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def test_cache_miss_returns_none(tmp_cache):
    assert api_client._cache_get("nonexistent_key") is None


def test_cache_round_trip(tmp_cache):
    api_client._cache_set("my_key", {"hello": "world"})
    result = api_client._cache_get("my_key")
    assert result == {"hello": "world"}


def test_cache_expired_returns_none(tmp_cache, monkeypatch):
    api_client._cache_set("old_key", {"data": 1})
    monkeypatch.setattr(api_client, "CACHE_TTL", -1)   # everything is expired
    assert api_client._cache_get("old_key") is None


def test_cache_overwrites_existing(tmp_cache):
    api_client._cache_set("key", {"v": 1})
    api_client._cache_set("key", {"v": 2})
    assert api_client._cache_get("key") == {"v": 2}


def test_cache_binary_round_trip(tmp_cache):
    data = b"\x89PNG\r\nfake image bytes"
    api_client._cache_set_binary("img_key", data)
    result = api_client._cache_get_binary("img_key")
    assert result == data


def test_cache_binary_miss_returns_none(tmp_cache):
    assert api_client._cache_get_binary("no_such_key") is None


# ---------------------------------------------------------------------------
# get_aircraft_photo_url
# ---------------------------------------------------------------------------

def test_photo_url_success(tmp_cache):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "photos": [{"thumbnail_large": {"src": "https://example.com/plane.jpg"}}]
    }
    with patch("api_client.requests.get", return_value=mock_resp):
        url = api_client.get_aircraft_photo_url("a1b2c3")
    assert url == "https://example.com/plane.jpg"


def test_photo_url_falls_back_to_small_thumbnail(tmp_cache):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "photos": [{"thumbnail": {"src": "https://example.com/small.jpg"}}]
    }
    with patch("api_client.requests.get", return_value=mock_resp):
        url = api_client.get_aircraft_photo_url("a1b2c3")
    assert url == "https://example.com/small.jpg"


def test_photo_url_no_photos_returns_none(tmp_cache):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"photos": []}
    with patch("api_client.requests.get", return_value=mock_resp):
        url = api_client.get_aircraft_photo_url("a1b2c3")
    assert url is None


def test_photo_url_cache_hit_skips_network(tmp_cache):
    api_client._cache_set("photourl_a1b2c3", {"url": "https://cached.com/photo.jpg"})
    with patch("api_client.requests.get") as mock_get:
        url = api_client.get_aircraft_photo_url("a1b2c3")
    mock_get.assert_not_called()
    assert url == "https://cached.com/photo.jpg"


def test_photo_url_empty_icao_returns_none(tmp_cache):
    assert api_client.get_aircraft_photo_url("") is None
    assert api_client.get_aircraft_photo_url(None) is None


def test_photo_url_network_error_returns_none(tmp_cache):
    with patch("api_client.requests.get", side_effect=Exception("timeout")):
        url = api_client.get_aircraft_photo_url("a1b2c3")
    assert url is None


def test_photo_url_cached_none_is_valid(tmp_cache):
    # A cached None means "we know there's no photo" — don't make another request
    api_client._cache_set("photourl_a1b2c3", {"url": None})
    with patch("api_client.requests.get") as mock_get:
        url = api_client.get_aircraft_photo_url("a1b2c3")
    mock_get.assert_not_called()
    assert url is None


# ---------------------------------------------------------------------------
# geolocate_by_ip
# ---------------------------------------------------------------------------

def test_geolocate_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "latitude": 47.6541,
        "longitude": -122.35,
        "city": "Seattle",
        "region": "Washington",
    }
    with patch("api_client.requests.get", return_value=mock_resp):
        result = api_client.geolocate_by_ip()
    assert result is not None
    lat, lon, name = result
    assert lat == pytest.approx(47.6541)
    assert lon == pytest.approx(-122.35)
    assert "Seattle" in name


def test_geolocate_missing_coords_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"city": "Unknown"}   # no lat/lon
    with patch("api_client.requests.get", return_value=mock_resp):
        result = api_client.geolocate_by_ip()
    assert result is None


def test_geolocate_network_error_returns_none():
    with patch("api_client.requests.get", side_effect=Exception("network error")):
        result = api_client.geolocate_by_ip()
    assert result is None


def test_geolocate_non_200_returns_none():
    mock_resp = MagicMock()
    mock_resp.status_code = 429   # rate limited
    with patch("api_client.requests.get", return_value=mock_resp):
        result = api_client.geolocate_by_ip()
    assert result is None


# ---------------------------------------------------------------------------
# get_flight_info
# ---------------------------------------------------------------------------

def test_flight_info_both_empty_returns_empty(tmp_cache):
    result = api_client.get_flight_info("", "")
    assert result == {}


def test_flight_info_cache_hit(tmp_cache):
    api_client._cache_set(
        "flightinfo_UAL123_a1b2c3", {"origin": "SEA", "destination": "LAX"}
    )
    result = api_client.get_flight_info("UAL123", "a1b2c3")
    assert result["origin"] == "SEA"
    assert result["destination"] == "LAX"


def test_flight_info_network_error_returns_dict(tmp_cache):
    with patch("api_client.requests.get", side_effect=Exception("timeout")):
        result = api_client.get_flight_info("UAL123", "a1b2c3")
    assert isinstance(result, dict)


def test_flight_info_result_is_cached(tmp_cache):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"response": {"flightroute": {}}}
    with patch("api_client.requests.get", return_value=mock_resp):
        api_client.get_flight_info("UAL123", "a1b2c3")
    # Second call must not hit network
    with patch("api_client.requests.get") as mock_get:
        api_client.get_flight_info("UAL123", "a1b2c3")
    mock_get.assert_not_called()


# ---------------------------------------------------------------------------
# fetch_photo_bytes
# ---------------------------------------------------------------------------

def test_fetch_photo_bytes_success(tmp_cache):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = b"fake image bytes"
    with patch("api_client.requests.get", return_value=mock_resp):
        data = api_client.fetch_photo_bytes("https://example.com/photo.jpg")
    assert data == b"fake image bytes"


def test_fetch_photo_bytes_none_url(tmp_cache):
    assert api_client.fetch_photo_bytes(None) is None
    assert api_client.fetch_photo_bytes("") is None


def test_fetch_photo_bytes_uses_cache(tmp_cache):
    url = "https://example.com/photo.jpg"
    key = f"photoimg_{hashlib.md5(url.encode()).hexdigest()}"
    api_client._cache_set_binary(key, b"cached bytes")
    with patch("api_client.requests.get") as mock_get:
        data = api_client.fetch_photo_bytes(url)
    mock_get.assert_not_called()
    assert data == b"cached bytes"


def test_fetch_photo_bytes_non_200_returns_none(tmp_cache):
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    with patch("api_client.requests.get", return_value=mock_resp):
        data = api_client.fetch_photo_bytes("https://example.com/photo.jpg")
    assert data is None


def test_fetch_photo_bytes_network_error_returns_none(tmp_cache):
    with patch("api_client.requests.get", side_effect=Exception("timeout")):
        data = api_client.fetch_photo_bytes("https://example.com/photo.jpg")
    assert data is None
