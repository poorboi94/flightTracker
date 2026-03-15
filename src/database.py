"""
SQLite flight history database.

Schema stores one row per aircraft visit (identified by ICAO hex + recency).
Rows are upserted on every poll cycle so live data stays current, then
automatically purged after 24 hours.

DB file: <project root>/data/flights.db
"""
import os
import sqlite3
import time

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "flights.db",
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS flights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    icao_hex        TEXT    NOT NULL,
    callsign        TEXT,
    lat             REAL,
    lon             REAL,
    altitude        INTEGER,
    alt_geom        INTEGER,
    speed           INTEGER,
    track           REAL,
    baro_rate       INTEGER,
    vert_trend      TEXT,
    squawk          TEXT,
    category        TEXT,
    tas             REAL,
    ias             REAL,
    mach            REAL,
    nav_heading     REAL,
    nav_altitude    INTEGER,
    rssi            REAL,
    distance        REAL,
    bearing         REAL,
    origin          TEXT,
    destination     TEXT,
    aircraft_type   TEXT,
    airline         TEXT,
    registration    TEXT,
    manufacturer    TEXT,
    model           TEXT,
    photo_url       TEXT,
    first_seen      REAL    NOT NULL,
    last_seen       REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_icao      ON flights(icao_hex);
CREATE INDEX IF NOT EXISTS idx_last_seen ON flights(last_seen);
CREATE INDEX IF NOT EXISTS idx_first_seen ON flights(first_seen);
"""

# A flight is considered the SAME visit if we've seen that ICAO hex within
# this window.  After 2 hours of silence we treat any reappearance as a new
# visit (e.g. a plane that circles the area twice in one day).
SAME_VISIT_WINDOW = 7200   # 2 hours


def init_db():
    """Create tables and indexes if they don't exist yet."""
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")     # safe for concurrent access
    return conn


def upsert_flight(ac):
    """
    Insert a new flight record or update an existing in-progress visit.

    ac is a dict from decoder.parse_aircraft(), optionally enriched with
    fields from api_client.get_flight_info() (origin, destination, …).
    """
    icao = ac.get("icao_hex")
    if not icao:
        return

    now = time.time()
    cutoff = now - SAME_VISIT_WINDOW

    with _connect() as conn:
        row = conn.execute(
            "SELECT id FROM flights WHERE icao_hex = ? AND last_seen > ? LIMIT 1",
            (icao, cutoff),
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE flights SET
                    callsign      = COALESCE(?, callsign),
                    lat           = ?,
                    lon           = ?,
                    altitude      = ?,
                    alt_geom      = COALESCE(?, alt_geom),
                    speed         = ?,
                    track         = ?,
                    baro_rate     = ?,
                    vert_trend    = ?,
                    squawk        = COALESCE(?, squawk),
                    category      = COALESCE(?, category),
                    tas           = COALESCE(?, tas),
                    ias           = COALESCE(?, ias),
                    mach          = COALESCE(?, mach),
                    nav_heading   = COALESCE(?, nav_heading),
                    nav_altitude  = COALESCE(?, nav_altitude),
                    rssi          = ?,
                    distance      = ?,
                    bearing       = ?,
                    origin        = COALESCE(?, origin),
                    destination   = COALESCE(?, destination),
                    aircraft_type = COALESCE(?, aircraft_type),
                    airline       = COALESCE(?, airline),
                    registration  = COALESCE(?, registration),
                    manufacturer  = COALESCE(?, manufacturer),
                    model         = COALESCE(?, model),
                    photo_url     = COALESCE(?, photo_url),
                    last_seen     = ?
                WHERE id = ?
                """,
                (
                    ac.get("callsign"),
                    ac.get("lat"), ac.get("lon"),
                    ac.get("altitude"), ac.get("alt_geom"),
                    ac.get("speed"), ac.get("track"),
                    ac.get("baro_rate"), ac.get("vert_trend"),
                    ac.get("squawk"), ac.get("category"),
                    ac.get("tas"), ac.get("ias"), ac.get("mach"),
                    ac.get("nav_heading"), ac.get("nav_altitude"),
                    ac.get("rssi"),
                    ac.get("distance"), ac.get("bearing"),
                    ac.get("origin"), ac.get("destination"),
                    ac.get("aircraft_type"), ac.get("airline"),
                    ac.get("registration"), ac.get("manufacturer"),
                    ac.get("model"), ac.get("photo_url"),
                    now, row["id"],
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO flights (
                    icao_hex, callsign, lat, lon, altitude, alt_geom,
                    speed, track, baro_rate, vert_trend, squawk, category,
                    tas, ias, mach, nav_heading, nav_altitude, rssi,
                    distance, bearing,
                    origin, destination, aircraft_type, airline,
                    registration, manufacturer, model, photo_url,
                    first_seen, last_seen
                ) VALUES (
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    ?,?,?,?,?,?,
                    ?,?,
                    ?,?,?,?,
                    ?,?,?,?,
                    ?,?
                )
                """,
                (
                    icao, ac.get("callsign"),
                    ac.get("lat"), ac.get("lon"),
                    ac.get("altitude"), ac.get("alt_geom"),
                    ac.get("speed"), ac.get("track"),
                    ac.get("baro_rate"), ac.get("vert_trend"),
                    ac.get("squawk"), ac.get("category"),
                    ac.get("tas"), ac.get("ias"), ac.get("mach"),
                    ac.get("nav_heading"), ac.get("nav_altitude"),
                    ac.get("rssi"),
                    ac.get("distance"), ac.get("bearing"),
                    ac.get("origin"), ac.get("destination"),
                    ac.get("aircraft_type"), ac.get("airline"),
                    ac.get("registration"), ac.get("manufacturer"),
                    ac.get("model"), ac.get("photo_url"),
                    now, now,
                ),
            )


def upsert_flights_batch(aircraft_list: list):
    """
    Upsert a list of aircraft records in a single SQLite transaction.
    Dramatically faster than calling upsert_flight() N times because SQLite
    only fsync's once per transaction instead of once per row.
    """
    if not aircraft_list:
        return
    now    = time.time()
    cutoff = now - SAME_VISIT_WINDOW

    with _connect() as conn:
        # Pre-fetch all existing visits in one query
        icao_list = [ac.get("icao_hex") for ac in aircraft_list if ac.get("icao_hex")]
        placeholders = ",".join("?" * len(icao_list))
        existing_rows = conn.execute(
            f"SELECT id, icao_hex FROM flights WHERE icao_hex IN ({placeholders}) AND last_seen > ?",
            icao_list + [cutoff],
        ).fetchall()
        existing = {r["icao_hex"]: r["id"] for r in existing_rows}

        for ac in aircraft_list:
            icao = ac.get("icao_hex")
            if not icao:
                continue

            if icao in existing:
                conn.execute(
                    """
                    UPDATE flights SET
                        callsign      = COALESCE(?, callsign),
                        lat=?, lon=?, altitude=?, alt_geom=COALESCE(?, alt_geom),
                        speed=?, track=?, baro_rate=?, vert_trend=?,
                        squawk=COALESCE(?, squawk), category=COALESCE(?, category),
                        tas=COALESCE(?, tas), ias=COALESCE(?, ias), mach=COALESCE(?, mach),
                        nav_heading=COALESCE(?, nav_heading),
                        nav_altitude=COALESCE(?, nav_altitude),
                        rssi=?, distance=?, bearing=?,
                        origin=COALESCE(?, origin), destination=COALESCE(?, destination),
                        aircraft_type=COALESCE(?, aircraft_type),
                        airline=COALESCE(?, airline),
                        registration=COALESCE(?, registration),
                        manufacturer=COALESCE(?, manufacturer),
                        model=COALESCE(?, model), photo_url=COALESCE(?, photo_url),
                        last_seen=?
                    WHERE id=?
                    """,
                    (
                        ac.get("callsign"),
                        ac.get("lat"), ac.get("lon"),
                        ac.get("altitude"), ac.get("alt_geom"),
                        ac.get("speed"), ac.get("track"),
                        ac.get("baro_rate"), ac.get("vert_trend"),
                        ac.get("squawk"), ac.get("category"),
                        ac.get("tas"), ac.get("ias"), ac.get("mach"),
                        ac.get("nav_heading"), ac.get("nav_altitude"),
                        ac.get("rssi"), ac.get("distance"), ac.get("bearing"),
                        ac.get("origin"), ac.get("destination"),
                        ac.get("aircraft_type"), ac.get("airline"),
                        ac.get("registration"), ac.get("manufacturer"),
                        ac.get("model"), ac.get("photo_url"),
                        now, existing[icao],
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO flights (
                        icao_hex, callsign, lat, lon, altitude, alt_geom,
                        speed, track, baro_rate, vert_trend, squawk, category,
                        tas, ias, mach, nav_heading, nav_altitude, rssi,
                        distance, bearing, origin, destination, aircraft_type,
                        airline, registration, manufacturer, model, photo_url,
                        first_seen, last_seen
                    ) VALUES (?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?,?, ?,?,?,?,?, ?,?,?,?,?, ?,?)
                    """,
                    (
                        icao, ac.get("callsign"),
                        ac.get("lat"), ac.get("lon"),
                        ac.get("altitude"), ac.get("alt_geom"),
                        ac.get("speed"), ac.get("track"),
                        ac.get("baro_rate"), ac.get("vert_trend"),
                        ac.get("squawk"), ac.get("category"),
                        ac.get("tas"), ac.get("ias"), ac.get("mach"),
                        ac.get("nav_heading"), ac.get("nav_altitude"),
                        ac.get("rssi"), ac.get("distance"), ac.get("bearing"),
                        ac.get("origin"), ac.get("destination"),
                        ac.get("aircraft_type"), ac.get("airline"),
                        ac.get("registration"), ac.get("manufacturer"),
                        ac.get("model"), ac.get("photo_url"),
                        now, now,
                    ),
                )
                existing[icao] = True  # don't try to insert again in same batch


def get_live_flights(max_age_seconds=10):
    """
    Return flights seen within the last max_age_seconds seconds.
    Sorted by distance (closest first).
    """
    cutoff = time.time() - max_age_seconds
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM flights WHERE last_seen > ? ORDER BY distance ASC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_history(hours=24):
    """
    Return all flights from the past N hours, newest first.
    Includes both live and recently-departed flights.
    """
    cutoff = time.time() - hours * 3600
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM flights WHERE first_seen > ? ORDER BY first_seen DESC",
            (cutoff,),
        ).fetchall()
    return [dict(r) for r in rows]


def purge_old_flights(hours=24):
    """Delete records whose last_seen is older than N hours."""
    cutoff = time.time() - hours * 3600
    with _connect() as conn:
        conn.execute("DELETE FROM flights WHERE last_seen < ?", (cutoff,))


def clear_history():
    """Delete all flight records from the database."""
    with _connect() as conn:
        conn.execute("DELETE FROM flights")
