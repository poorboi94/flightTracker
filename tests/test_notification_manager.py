"""
Tests for notification_manager.py — new aircraft detection, brief/summary
notifications, fast mode, and queue behaviour.
"""
import time

import pytest

from notification_manager import NotificationManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ac(icao, callsign=None):
    return {"icao_hex": icao, "callsign": callsign or icao}


def initialized_nm(*initial_icaos):
    """Return a NotificationManager that has already seen the given ICAOs."""
    nm = NotificationManager()
    nm.update([make_ac(i) for i in initial_icaos])
    return nm


# ---------------------------------------------------------------------------
# First call — silent absorption
# ---------------------------------------------------------------------------

def test_first_call_suppresses_notifications_not_return_value():
    # update() returns the mathematically-new aircraft, but the notification
    # system silently absorbs the first batch so no popups fire.
    nm = NotificationManager()
    nm.update([make_ac("aaa"), make_ac("bbb")])


def test_first_call_no_brief_notification():
    nm = NotificationManager()
    nm.update([make_ac("aaa")])
    assert nm.get_brief_notification() is None


def test_first_call_no_summary_overlay():
    nm = NotificationManager()
    nm.update([make_ac("aaa"), make_ac("bbb"), make_ac("ccc")])
    assert nm.get_summary_overlay() is None


def test_first_call_no_fast_mode():
    nm = NotificationManager()
    nm.update([make_ac("aaa")])
    assert nm.fast_mode is False


# ---------------------------------------------------------------------------
# Single new aircraft → brief popup
# ---------------------------------------------------------------------------

def test_single_new_aircraft_returned():
    nm = initialized_nm()
    new = nm.update([make_ac("aaa")])
    assert len(new) == 1
    assert new[0]["icao_hex"] == "aaa"


def test_single_new_queues_brief():
    nm = initialized_nm()
    nm.update([make_ac("aaa")])
    notif = nm.get_brief_notification()
    assert notif is not None
    assert notif["icao_hex"] == "aaa"


def test_two_new_queues_two_briefs():
    nm = initialized_nm()
    nm.update([make_ac("aaa"), make_ac("bbb")])
    first = nm.get_brief_notification()
    assert first["icao_hex"] == "aaa"
    # Expire the first
    nm._current_start = time.time() - NotificationManager.BRIEF_DURATION - 1
    second = nm.get_brief_notification()
    assert second["icao_hex"] == "bbb"


def test_two_new_does_not_trigger_summary():
    nm = initialized_nm()
    nm.update([make_ac("aaa"), make_ac("bbb")])
    assert nm.get_summary_overlay() is None


# ---------------------------------------------------------------------------
# 3+ new aircraft → summary overlay
# ---------------------------------------------------------------------------

def test_three_new_triggers_summary():
    nm = initialized_nm()
    nm.update([make_ac("a"), make_ac("b"), make_ac("c")])
    result = nm.get_summary_overlay()
    assert result is not None
    aircraft_list, countdown = result
    assert len(aircraft_list) == 3


def test_summary_countdown_is_positive():
    nm = initialized_nm()
    nm.update([make_ac("a"), make_ac("b"), make_ac("c")])
    _, countdown = nm.get_summary_overlay()
    assert countdown >= 1


def test_summary_countdown_decreases_over_time():
    nm = initialized_nm()
    nm.update([make_ac("a"), make_ac("b"), make_ac("c")])
    _, c1 = nm.get_summary_overlay()
    nm._summary_start = time.time() - 2
    _, c2 = nm.get_summary_overlay()
    assert c2 < c1


def test_summary_expires_after_duration():
    nm = initialized_nm()
    nm.update([make_ac("a"), make_ac("b"), make_ac("c")])
    nm._summary_start = time.time() - NotificationManager.SUMMARY_DURATION - 1
    assert nm.get_summary_overlay() is None


def test_summary_clears_brief_queue():
    nm = initialized_nm()
    nm.update([make_ac("z")])          # one brief queued
    nm.update([make_ac("a"), make_ac("b"), make_ac("c")])   # triggers summary
    assert nm._queue == []
    assert nm._current is None


def test_four_new_all_in_summary():
    nm = initialized_nm()
    nm.update([make_ac("a"), make_ac("b"), make_ac("c"), make_ac("d")])
    aircraft_list, _ = nm.get_summary_overlay()
    assert len(aircraft_list) == 4


# ---------------------------------------------------------------------------
# Fast mode
# ---------------------------------------------------------------------------

def test_fast_mode_activated_on_single_new():
    nm = initialized_nm()
    nm.update([make_ac("aaa")])
    assert nm.fast_mode is True


def test_fast_mode_activated_on_summary():
    nm = initialized_nm()
    nm.update([make_ac("a"), make_ac("b"), make_ac("c")])
    assert nm.fast_mode is True


def test_fast_mode_not_activated_when_no_new():
    nm = initialized_nm("aaa")
    nm.update([make_ac("aaa")])
    assert nm.fast_mode is False


def test_fast_mode_expires():
    nm = initialized_nm()
    nm.update([make_ac("aaa")])
    assert nm.fast_mode is True
    nm._fast_start = time.time() - NotificationManager.FAST_MODE_DURATION - 1
    nm.update([make_ac("aaa")])   # trigger expiry check with no new aircraft
    assert nm.fast_mode is False


def test_fast_mode_resets_timer_on_new_aircraft():
    nm = initialized_nm()
    nm.update([make_ac("aaa")])
    first_start = nm._fast_start
    time.sleep(0.01)
    nm.update([make_ac("bbb")])
    assert nm._fast_start > first_start


# ---------------------------------------------------------------------------
# Brief popup expiry and queue
# ---------------------------------------------------------------------------

def test_brief_popup_expires_after_duration():
    nm = initialized_nm()
    nm.update([make_ac("aaa")])
    assert nm.get_brief_notification() is not None
    nm._current_start = time.time() - NotificationManager.BRIEF_DURATION - 1
    assert nm.get_brief_notification() is None


def test_brief_queue_drains_in_order():
    nm = initialized_nm()
    nm.update([make_ac("aaa"), make_ac("bbb")])
    first = nm.get_brief_notification()
    assert first["icao_hex"] == "aaa"
    nm._current_start = time.time() - NotificationManager.BRIEF_DURATION - 1
    second = nm.get_brief_notification()
    assert second["icao_hex"] == "bbb"
    nm._current_start = time.time() - NotificationManager.BRIEF_DURATION - 1
    assert nm.get_brief_notification() is None   # queue empty


def test_brief_popup_not_shown_before_duration():
    nm = initialized_nm()
    nm.update([make_ac("aaa"), make_ac("bbb")])
    nm.get_brief_notification()   # start showing "aaa"
    # Don't expire — still showing "aaa"
    notif = nm.get_brief_notification()
    assert notif["icao_hex"] == "aaa"


# ---------------------------------------------------------------------------
# remove_aircraft — allows re-detection
# ---------------------------------------------------------------------------

def test_remove_aircraft_allows_redetection():
    nm = initialized_nm("aaa")
    nm.remove_aircraft("aaa")
    new = nm.update([make_ac("aaa")])
    assert len(new) == 1


def test_remove_unknown_aircraft_is_noop():
    nm = initialized_nm()
    nm.remove_aircraft("unknown_icao")   # should not raise


# ---------------------------------------------------------------------------
# No duplicates for known aircraft
# ---------------------------------------------------------------------------

def test_known_aircraft_not_reported_again():
    nm = initialized_nm("aaa")
    new = nm.update([make_ac("aaa")])
    assert new == []
    assert nm.get_brief_notification() is None


def test_only_new_icaos_returned():
    nm = initialized_nm("aaa")
    new = nm.update([make_ac("aaa"), make_ac("bbb")])
    assert len(new) == 1
    assert new[0]["icao_hex"] == "bbb"


# ---------------------------------------------------------------------------
# Aircraft that disappears then reappears
# ---------------------------------------------------------------------------

def test_departed_aircraft_reappears_as_new():
    nm = initialized_nm("aaa")
    # aaa departs
    nm.update([])
    # aaa reappears — now it's new again
    new = nm.update([make_ac("aaa")])
    assert len(new) == 1


def test_remove_then_reappear_with_others():
    nm = initialized_nm("aaa", "bbb")
    nm.remove_aircraft("aaa")
    new = nm.update([make_ac("aaa"), make_ac("bbb")])
    icaos = [a["icao_hex"] for a in new]
    assert "aaa" in icaos
    assert "bbb" not in icaos
