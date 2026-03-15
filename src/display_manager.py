"""
Display manager — sleep/wake and nighttime scheduling.

On the Raspberry Pi 5 the display is put to sleep via the vcgencmd utility
(or xset dpms on an X session).  On a desktop/laptop in development mode
these calls are skipped but the sleep state is still tracked so the rest of
the app behaves correctly (e.g. the main loop doesn't render while "asleep").
"""
import datetime
import platform
import subprocess
import time


def _is_pi():
    """Best-effort check: are we running on a Raspberry Pi?"""
    try:
        with open("/proc/device-tree/model", "r") as f:
            return "raspberry pi" in f.read().lower()
    except Exception:
        pass
    machine = platform.machine().lower()
    return machine.startswith("aarch") or machine == "armv7l"


class DisplayManager:
    """
    Tracks whether the display should be sleeping and manages hardware calls.

    Sleep triggers:
      - User idle for longer than idle_timeout_minutes (only when no live
        aircraft are on screen — aircraft activity resets the idle timer).
      - Current time falls in the nighttime window [night_start, night_end).

    Wake triggers:
      - touch() is called (button press or screen tap).
      - A new aircraft appears while sleeping (handled by the main loop calling
        touch() when notifications arrive).
    """

    def __init__(
        self,
        idle_timeout_minutes: int = 5,
        night_start: int = 23,
        night_end: int = 6,
    ):
        self.idle_timeout = idle_timeout_minutes * 60
        self.night_start = night_start
        self.night_end = night_end

        self._last_activity = time.time()
        self._sleeping = False
        self._on_pi = _is_pi()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def touch(self):
        """Record user activity (touch / button press). Wakes display if sleeping."""
        self._last_activity = time.time()
        if self._sleeping:
            self._wake()

    def update(self, has_live_aircraft: bool = True):
        """
        Call once per main-loop iteration.

        has_live_aircraft — when True the idle timer is reset (we don't sleep
        while actively tracking planes).
        """
        now = time.time()

        if has_live_aircraft:
            self._last_activity = now

        idle = now - self._last_activity
        should_sleep = (idle >= self.idle_timeout) or self._is_night()

        if should_sleep and not self._sleeping:
            self._sleep()
        elif not should_sleep and self._sleeping:
            self._wake()

    @property
    def is_sleeping(self) -> bool:
        return self._sleeping

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_night(self) -> bool:
        hour = datetime.datetime.now().hour
        if self.night_start > self.night_end:
            # Crosses midnight  e.g. 23 → 06
            return hour >= self.night_start or hour < self.night_end
        return self.night_start <= hour < self.night_end

    def _sleep(self):
        self._sleeping = True
        if self._on_pi:
            # Raspberry Pi: turn off HDMI output
            try:
                subprocess.run(
                    ["vcgencmd", "display_power", "0"],
                    capture_output=True,
                    timeout=3,
                )
            except Exception:
                pass

    def _wake(self):
        self._sleeping = False
        self._last_activity = time.time()
        if self._on_pi:
            try:
                subprocess.run(
                    ["vcgencmd", "display_power", "1"],
                    capture_output=True,
                    timeout=3,
                )
            except Exception:
                pass
