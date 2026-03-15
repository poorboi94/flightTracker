"""
Notification manager — detects new aircraft and drives the notification UI.

Three notification types defined in the task spec:

  Brief popup    Single new aircraft appears. Shows a 200×80 px card in the
                 top-right corner for 3 seconds.  Multiple arrivals are queued
                 and shown one after another.

  Summary overlay  3 or more new aircraft arrive at once (e.g. after the app
                   starts up). Shows a full-screen semi-transparent overlay
                   listing them with a 5-second countdown.

  Fast mode      Whenever any new aircraft is detected, the auto-rotate
                 interval drops from 5 minutes to 30 seconds for 60 seconds,
                 so the user quickly sees the new arrivals.
"""
import time


class NotificationManager:

    BRIEF_DURATION      = 3.0    # seconds each brief popup is shown
    SUMMARY_THRESHOLD   = 3      # N+ new aircraft → summary overlay instead
    SUMMARY_DURATION    = 5.0    # countdown seconds for the summary overlay
    FAST_MODE_DURATION  = 60.0   # seconds fast-rotate stays active

    def __init__(self):
        self._known_icao: set = set()
        self._initialized: bool = False    # True after the first poll completes

        # Brief popup queue
        self._queue: list = []               # list of aircraft dicts
        self._current: dict | None = None    # aircraft being shown now
        self._current_start: float = 0.0

        # Summary overlay
        self._summary_aircraft: list = []
        self._summary_start: float = 0.0
        self._summary_active: bool = False

        # Fast mode
        self.fast_mode: bool = False
        self._fast_start: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, live_aircraft: list) -> list:
        """
        Call once per poll cycle with the current list of live aircraft dicts.

        Updates internal state, activates notifications, and returns the list
        of aircraft that are brand-new since the last call.
        """
        current_icao = {ac["icao_hex"] for ac in live_aircraft if ac.get("icao_hex")}
        new_icao = current_icao - self._known_icao
        self._known_icao = current_icao

        new_aircraft = [ac for ac in live_aircraft if ac.get("icao_hex") in new_icao]

        if not self._initialized:
            # Silently absorb the first batch — these are already-flying planes,
            # not new arrivals, so don't show popups or trigger fast mode.
            self._initialized = True
        elif new_aircraft:
            self._activate(new_aircraft)

        # Expire fast mode
        if self.fast_mode and time.time() - self._fast_start >= self.FAST_MODE_DURATION:
            self.fast_mode = False

        return new_aircraft

    def get_brief_notification(self) -> "dict | None":
        """
        Return the aircraft dict for the brief popup that should be shown
        right now, or None.

        Advances the queue automatically when the current popup has been
        visible long enough.
        """
        now = time.time()

        # Expire current popup
        if self._current is not None:
            if now - self._current_start >= self.BRIEF_DURATION:
                self._current = None

        # Advance queue
        if self._current is None and self._queue:
            self._current = self._queue.pop(0)
            self._current_start = now

        return self._current

    def get_summary_overlay(self) -> "tuple | None":
        """
        If a summary overlay is active, return (aircraft_list, countdown_int).
        Returns None when inactive or expired.
        """
        if not self._summary_active:
            return None

        elapsed = time.time() - self._summary_start
        remaining = self.SUMMARY_DURATION - elapsed
        if remaining <= 0:
            self._summary_active = False
            return None

        countdown = max(1, int(remaining) + 1)
        return self._summary_aircraft, countdown

    def remove_aircraft(self, icao_hex: str):
        """Call when an aircraft leaves the live feed so we notice if it returns."""
        self._known_icao.discard(icao_hex)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _activate(self, new_aircraft: list):
        """Decide whether to show brief popups or a summary overlay."""
        if len(new_aircraft) >= self.SUMMARY_THRESHOLD:
            # Summary overlay takes priority over brief queue
            self._summary_aircraft = new_aircraft
            self._summary_start = time.time()
            self._summary_active = True
            # Clear any stale brief queue so we don't double-notify
            self._queue.clear()
            self._current = None
        else:
            self._queue.extend(new_aircraft)

        # Always activate fast mode on any new arrival
        self.fast_mode = True
        self._fast_start = time.time()
