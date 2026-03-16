"""
Tests for database.py — insert, update, query, purge, clear.
All tests use a temp SQLite file via the tmp_db fixture (see conftest.py).
"""
import sqlite3
import time

import pytest

import database


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ac(icao="a1b2c3", callsign="UAL123", distance=20.0):
    return {
        "icao_hex":     icao,
        "callsign":     callsign,
        "lat":          47.9,
        "lon":          -122.1,
        "altitude":     35000,
        "alt_geom":     None,
        "speed":        450,
        "track":        90.0,
        "baro_rate":    0,
        "vert_trend":   "level",
        "squawk":       "1234",
        "category":     "A3",
        "tas":          None,
        "ias":          None,
        "mach":         None,
        "nav_heading":  None,
        "nav_altitude": None,
        "rssi":         None,
        "distance":     distance,
        "bearing":      45.0,
        "last_seen":    time.time(),
        "messages":     100,
        "seen":         1,
        "seen_pos":     1,
        "origin":       "SEA",
        "destination":  "LAX",
        "airline":      "United",
        "aircraft_type":"B737",
        "model":        "737-800",
        "registration": "N12345",
        "manufacturer": "Boeing",
        "photo_url":    None,
    }


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

def test_init_db_creates_flights_table(tmp_db):
    conn = sqlite3.connect(tmp_db)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "flights" in tables


def test_init_db_creates_indexes(tmp_db):
    conn = sqlite3.connect(tmp_db)
    indexes = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()]
    assert "idx_icao" in indexes
    assert "idx_last_seen" in indexes


def test_init_db_idempotent(tmp_db):
    # Calling init_db twice should not raise
    database.init_db()
    database.init_db()


# ---------------------------------------------------------------------------
# upsert_flight — insert
# ---------------------------------------------------------------------------

def test_upsert_inserts_new_record(tmp_db):
    database.upsert_flight(make_ac())
    live = database.get_live_flights(max_age_seconds=60)
    assert len(live) == 1
    assert live[0]["icao_hex"] == "a1b2c3"
    assert live[0]["callsign"] == "UAL123"
    assert live[0]["altitude"] == 35000


def test_upsert_no_icao_is_ignored(tmp_db):
    ac = make_ac()
    ac["icao_hex"] = ""
    database.upsert_flight(ac)
    assert database.get_live_flights(max_age_seconds=60) == []


def test_upsert_sets_first_seen_and_last_seen(tmp_db):
    before = time.time()
    database.upsert_flight(make_ac())
    after = time.time()
    live = database.get_live_flights(max_age_seconds=60)
    assert before <= live[0]["first_seen"] <= after
    assert before <= live[0]["last_seen"] <= after


# ---------------------------------------------------------------------------
# upsert_flight — update (same visit window)
# ---------------------------------------------------------------------------

def test_upsert_updates_existing_row(tmp_db):
    database.upsert_flight(make_ac())
    ac2 = make_ac(callsign="UAL123")
    ac2["altitude"] = 36000
    database.upsert_flight(ac2)
    live = database.get_live_flights(max_age_seconds=60)
    assert len(live) == 1          # still one row
    assert live[0]["altitude"] == 36000


def test_upsert_coalesce_keeps_existing_callsign(tmp_db):
    database.upsert_flight(make_ac())
    ac2 = make_ac()
    ac2["callsign"] = None         # None should not overwrite existing value
    database.upsert_flight(ac2)
    live = database.get_live_flights(max_age_seconds=60)
    assert live[0]["callsign"] == "UAL123"


def test_upsert_coalesce_keeps_existing_origin(tmp_db):
    database.upsert_flight(make_ac())
    ac2 = make_ac()
    ac2["origin"] = None
    database.upsert_flight(ac2)
    live = database.get_live_flights(max_age_seconds=60)
    assert live[0]["origin"] == "SEA"


def test_upsert_new_value_overwrites_when_non_none(tmp_db):
    ac = make_ac()
    ac["origin"] = None
    database.upsert_flight(ac)
    ac2 = make_ac()
    ac2["origin"] = "PDX"
    database.upsert_flight(ac2)
    live = database.get_live_flights(max_age_seconds=60)
    assert live[0]["origin"] == "PDX"


# ---------------------------------------------------------------------------
# upsert_flights_batch
# ---------------------------------------------------------------------------

def test_batch_inserts_multiple(tmp_db):
    aircraft = [make_ac("aaa111", "AAL1"), make_ac("bbb222", "DAL2"), make_ac("ccc333", "UAL3")]
    database.upsert_flights_batch(aircraft)
    live = database.get_live_flights(max_age_seconds=60)
    assert len(live) == 3


def test_batch_updates_existing(tmp_db):
    database.upsert_flight(make_ac())
    ac2 = make_ac()
    ac2["altitude"] = 40000
    database.upsert_flights_batch([ac2])
    live = database.get_live_flights(max_age_seconds=60)
    assert len(live) == 1
    assert live[0]["altitude"] == 40000


def test_batch_no_duplicate_for_same_icao_in_one_batch(tmp_db):
    # Two entries with the same ICAO in a single batch — should produce one row
    database.upsert_flights_batch([make_ac("aaa111"), make_ac("aaa111")])
    live = database.get_live_flights(max_age_seconds=60)
    assert len(live) == 1


def test_batch_empty_list_is_noop(tmp_db):
    database.upsert_flights_batch([])
    assert database.get_live_flights(max_age_seconds=60) == []


def test_batch_skips_entries_without_icao(tmp_db):
    ac = make_ac()
    ac["icao_hex"] = None
    database.upsert_flights_batch([ac])
    assert database.get_live_flights(max_age_seconds=60) == []


# ---------------------------------------------------------------------------
# get_live_flights
# ---------------------------------------------------------------------------

def test_live_flights_sorted_by_distance(tmp_db):
    database.upsert_flights_batch([
        make_ac("far0001", distance=200.0),
        make_ac("near001", distance=10.0),
        make_ac("mid0001", distance=50.0),
    ])
    live = database.get_live_flights(max_age_seconds=60)
    distances = [r["distance"] for r in live]
    assert distances == sorted(distances)
    assert live[0]["icao_hex"] == "near001"


def test_live_flights_excludes_stale(tmp_db):
    database.upsert_flight(make_ac())
    # max_age_seconds=0 means cutoff is right now — nothing qualifies
    live = database.get_live_flights(max_age_seconds=0)
    assert len(live) == 0


def test_live_flights_returns_recent(tmp_db):
    database.upsert_flight(make_ac())
    live = database.get_live_flights(max_age_seconds=60)
    assert len(live) == 1


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------

def test_get_history_returns_all_within_window(tmp_db):
    database.upsert_flights_batch([make_ac("aaa111"), make_ac("bbb222")])
    history = database.get_history(hours=24)
    assert len(history) == 2


def test_get_history_ordered_newest_first(tmp_db):
    database.upsert_flight(make_ac("aaa111"))
    time.sleep(0.05)
    database.upsert_flight(make_ac("bbb222"))
    history = database.get_history(hours=24)
    assert history[0]["icao_hex"] == "bbb222"


def test_get_history_excludes_old(tmp_db):
    database.upsert_flight(make_ac())
    # hours=0 means cutoff is right now — nothing qualifies
    history = database.get_history(hours=0)
    assert len(history) == 0


# ---------------------------------------------------------------------------
# purge_old_flights
# ---------------------------------------------------------------------------

def test_purge_removes_old_records(tmp_db):
    database.upsert_flight(make_ac())
    database.purge_old_flights(hours=0)   # purge everything
    assert database.get_live_flights(max_age_seconds=60) == []


def test_purge_keeps_recent_records(tmp_db):
    database.upsert_flight(make_ac())
    database.purge_old_flights(hours=24)
    assert len(database.get_live_flights(max_age_seconds=60)) == 1


# ---------------------------------------------------------------------------
# clear_history
# ---------------------------------------------------------------------------

def test_clear_history_wipes_all(tmp_db):
    database.upsert_flights_batch([make_ac("aaa111"), make_ac("bbb222")])
    database.clear_history()
    assert database.get_history(hours=24) == []
    assert database.get_live_flights(max_age_seconds=60) == []
