"""
Flight Tracker — main entry point.

Usage
─────
  python src/main.py --desktop   # windowed, for laptop dev (no Pi hardware)
  python src/main.py             # fullscreen, for Raspberry Pi

Architecture
────────────
The main thread does ONE thing: handle pygame events and render frames.
It never touches the network or the database.

A single DataFetcher daemon thread owns all I/O:
  • Polls dump1090 every 2 seconds (HTTP)
  • Batch-upserts positioned aircraft to SQLite in one transaction
  • Fires metadata/photo fetches in further daemon threads (one per new aircraft)
  • Refreshes the "history" query only every 10 seconds
  • Writes results into shared, lock-protected state

The main thread reads that shared state lock-free-ish (Python GIL + simple list
replacement makes the reads safe) and renders at up to 60 fps with zero I/O
jank.
"""
import argparse
import os
import sys
import threading
import time

import pygame

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config as cfg_module
import database
import decoder
import wifi_setup
from api_client import get_flight_info, get_aircraft_photo_url
from display_manager import DisplayManager
from notification_manager import NotificationManager
from ui import FlightUI

# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------
POLL_INTERVAL    = 2.0    # seconds between ADS-B polls
HISTORY_INTERVAL = 10.0   # seconds between history DB queries (expensive)
PURGE_INTERVAL   = 3600.0 # seconds between 24-hour purge passes
TARGET_FPS       = 60     # render target — plenty of headroom on Pi 5


# ---------------------------------------------------------------------------
# Metadata fetcher (one daemon thread per new aircraft)
# ---------------------------------------------------------------------------

def _fetch_metadata(ac: dict, config: dict, fetched_icao: set, lock: threading.Lock):
    """Enrich one aircraft with route/photo data, then upsert the result."""
    callsign = (ac.get("callsign") or "").strip()
    icao     = ac.get("icao_hex", "")
    info     = get_flight_info(callsign, icao)
    ac.update(info)
    photo_url = get_aircraft_photo_url(icao)
    if photo_url:
        ac["photo_url"] = photo_url
    database.upsert_flight(ac)
    # If we got no route data, remove from fetched set so it retries next poll
    if not info.get("origin") and not info.get("destination"):
        with lock:
            fetched_icao.discard(icao)


# ---------------------------------------------------------------------------
# DataFetcher — the only thread allowed to do I/O
# ---------------------------------------------------------------------------

class DataFetcher(threading.Thread):
    """
    Background daemon thread.  Polls ADS-B and updates the database.
    Exposes the latest data to the main thread via get_state().
    """

    def __init__(self, config: dict, notif_mgr: NotificationManager):
        super().__init__(daemon=True, name="DataFetcher")
        self._config    = config
        self._notif_mgr = notif_mgr

        # Shared state (written here, read by main thread)
        self._lock          = threading.Lock()
        self._live:         list = []
        self._history:      list = []
        self._has_new:      bool = False   # new aircraft arrived since last get_state()

        self._fetched_icao:   set  = set()
        self._new_aircraft:   list = []
        self._last_history:   float = 0.0
        self._last_purge:     float = 0.0
        self._running:        bool = True

    # ── Public API (called from main thread) ───────────────────────────

    def get_state(self):
        """
        Return (live_aircraft, history_flights, had_new_aircraft).
        had_new_aircraft is True only once per batch of new arrivals.
        """
        with self._lock:
            had_new            = self._has_new
            self._has_new      = False
            new_ac             = list(self._new_aircraft)
            self._new_aircraft = []
            return self._live, self._history, had_new, new_ac

    def stop(self):
        self._running = False

    # ── Thread body ────────────────────────────────────────────────────

    def run(self):
        cfg         = self._config
        dump1090    = cfg.get("dump1090_url",    "http://localhost:8080")
        home_lat    = cfg.get("lat",              47.6062)
        home_lon    = cfg.get("lon",             -122.3321)
        max_range   = cfg.get("max_range_miles",  250)
        history_hrs = cfg.get("history_hours",    24)

        while self._running:
            t0 = time.monotonic()
            try:
                self._poll(dump1090, home_lat, home_lon, max_range, history_hrs)
            except Exception:
                pass  # never let a transient error crash the fetcher
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, POLL_INTERVAL - elapsed))

    def _poll(self, dump1090, home_lat, home_lon, max_range, history_hrs):
        now = time.monotonic()

        # ── 1. Fetch raw ADS-B data ──────────────────────────────────
        raw_list = decoder.get_aircraft(dump1090)
        parsed   = []
        for raw in raw_list:
            ac = decoder.parse_aircraft(raw, home_lat, home_lon)
            if ac is None or ac["distance"] > max_range:
                continue
            parsed.append(ac)

        # ── 2. Batch-upsert to DB in one transaction ─────────────────
        if parsed:
            database.upsert_flights_batch(parsed)

        # ── 3. Metadata fetch for first-seen aircraft ─────────────────
        for ac in parsed:
            icao = ac["icao_hex"]
            if icao not in self._fetched_icao:
                self._fetched_icao.add(icao)
                threading.Thread(
                    target=_fetch_metadata,
                    args=(dict(ac), self._config, self._fetched_icao, self._lock),
                    daemon=True,
                ).start()

        # ── 4. Notification manager ───────────────────────────────────
        new_ac = self._notif_mgr.update(parsed)

        # ── 5. Refresh live aircraft from DB (enriched by metadata) ──
        live = database.get_live_flights(max_age_seconds=POLL_INTERVAL * 3)

        # ── 6. Refresh history (throttled) ───────────────────────────
        history = None
        if now - self._last_history >= HISTORY_INTERVAL:
            history = database.get_history(hours=history_hrs)
            self._last_history = now

        # ── 7. Periodic purge ─────────────────────────────────────────
        if now - self._last_purge >= PURGE_INTERVAL:
            self._last_purge = now
            database.purge_old_flights(hours=history_hrs)
            self._fetched_icao.clear()

        # ── 8. Publish results (one short lock window) ────────────────
        with self._lock:
            self._live = live
            if history is not None:
                self._history = history
            if new_ac:
                self._has_new      = True
                self._new_aircraft = new_ac


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Personal Flight Tracker")
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="Run windowed (development / desktop mode)",
    )
    args = parser.parse_args()

    # On the Pi, show the Wi-Fi setup screen if there is no network.
    # Skip this entirely in desktop/development mode.
    if not args.desktop and not wifi_setup.has_network():
        result = wifi_setup.run_wifi_setup(desktop=False)
        if result == "quit":
            return
        # "connected" or "skipped" — either way, continue to the main app

    config = cfg_module.load_config()
    database.init_db()

    notif_mgr = NotificationManager()
    disp_mgr  = DisplayManager(
        idle_timeout_minutes = config.get("idle_timeout_minutes", 5),
        night_start          = config.get("night_mode_start", 23),
        night_end            = config.get("night_mode_end", 6),
    )

    ui = FlightUI(config, desktop=args.desktop)
    ui.init()

    # Start background I/O thread
    fetcher = DataFetcher(config, notif_mgr)
    fetcher.start()

    # Main thread: events + render only
    live_aircraft:   list = []
    history_flights: list = []

    running = True
    while running:

        # ── Events (must be fast — no blocking work here) ─────────────
        for event in pygame.event.get():
            result = ui.handle_event(event)
            if result == "quit":
                running = False
                break
            if event.type in (pygame.MOUSEBUTTONDOWN, pygame.KEYDOWN, pygame.FINGERDOWN):
                disp_mgr.touch()

        if not running:
            break

        # ── Read latest data from background thread ───────────────────
        live_aircraft, history_flights, had_new, new_aircraft = fetcher.get_state()
        if had_new:
            disp_mgr.touch()

        # ── Notification state ────────────────────────────────────────
        notification = notif_mgr.get_brief_notification()
        summary      = notif_mgr.get_summary_overlay()

        # ── Display sleep/wake ────────────────────────────────────────
        disp_mgr.update(has_live_aircraft=bool(live_aircraft))

        # ── Render ────────────────────────────────────────────────────
        if not disp_mgr.is_sleeping:
            ui.update(
                live_aircraft   = live_aircraft,
                history_flights = history_flights,
                notification    = notification,
                summary         = summary,
                fast_mode       = notif_mgr.fast_mode,
                new_aircraft    = new_aircraft,
            )
            ui.draw()
        else:
            time.sleep(0.05)

    fetcher.stop()
    ui.quit()


if __name__ == "__main__":
    main()
