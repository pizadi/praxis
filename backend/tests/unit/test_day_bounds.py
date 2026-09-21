"""APP_TZ day-boundary helper (app/db/session.py::day_bounds)."""

import datetime as dt

import pytest

from app.db.session import APP_TZ, day_bounds


def test_bounds_cover_the_whole_day_in_app_tz():
    lo, hi = day_bounds(dt.date(2026, 9, 21))
    assert lo.tzinfo is APP_TZ
    assert dt.datetime(2026, 9, 21, 0, 0, tzinfo=APP_TZ) == lo
    assert dt.datetime(2026, 9, 21, 23, 59, 59, 999999, tzinfo=APP_TZ) == hi


def test_midday_instant_is_inside_its_own_tehran_day():
    lo, hi = day_bounds(dt.date(2026, 9, 21))
    noon = dt.datetime(2026, 9, 21, 12, 0, tzinfo=APP_TZ)
    assert lo <= noon <= hi


def test_utc_midnight_may_belong_to_the_previous_tehran_day():
    """00:00 UTC = 03:30 Tehran (same day); 21:00 UTC = 00:30 Tehran NEXT
    day — the payments/day-view boundary trap (~20:30–24:00 UTC)."""
    lo21, hi21 = day_bounds(dt.date(2026, 9, 21))
    lo22, hi22 = day_bounds(dt.date(2026, 9, 22))
    utc_midnight = dt.datetime(2026, 9, 21, 0, 0, tzinfo=dt.UTC)
    utc_2100 = dt.datetime(2026, 9, 21, 21, 0, tzinfo=dt.UTC)
    assert lo21 <= utc_midnight <= hi21
    assert not (lo21 <= utc_2100 <= hi21)
    assert lo22 <= utc_2100 <= hi22


@pytest.mark.parametrize("day", [dt.date(2026, 1, 1), dt.date(2026, 3, 21)])
def test_works_year_round(day):
    lo, hi = day_bounds(day)
    assert lo < hi
