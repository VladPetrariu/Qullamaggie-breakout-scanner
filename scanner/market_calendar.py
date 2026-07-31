"""NYSE trading calendar — rule-based, no external dependency.

Covers the ten regular NYSE holidays with weekend observance shifts.
Unscheduled closures (e.g. days of mourning) are not modeled; the
preflight data gate is the backstop for those.
"""

from __future__ import annotations

from datetime import date, timedelta


def easter_sunday(year: int) -> date:
    """Gregorian Easter (Anonymous Gregorian computus)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) given weekday (Mon=0) of a month."""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _observed(d: date) -> date | None:
    """NYSE observance: Saturday holidays move to Friday, Sunday to Monday.
    Returns None when the holiday is not observed at all (New Year's Day
    on a Saturday — NYSE does not close the preceding Dec 31)."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def nyse_holidays(year: int) -> set[date]:
    days: set[date] = set()

    new_year = date(year, 1, 1)
    if new_year.weekday() == 6:
        days.add(new_year + timedelta(days=1))
    elif new_year.weekday() != 5:  # Saturday New Year is not observed
        days.add(new_year)

    days.add(_nth_weekday(year, 1, 0, 3))    # MLK Day
    days.add(_nth_weekday(year, 2, 0, 3))    # Washington's Birthday
    days.add(easter_sunday(year) - timedelta(days=2))  # Good Friday
    days.add(_last_weekday(year, 5, 0))      # Memorial Day
    if year >= 2022:
        juneteenth = _observed(date(year, 6, 19))
        if juneteenth:
            days.add(juneteenth)
    independence = _observed(date(year, 7, 4))
    if independence:
        days.add(independence)
    days.add(_nth_weekday(year, 9, 0, 1))    # Labor Day
    days.add(_nth_weekday(year, 11, 3, 4))   # Thanksgiving
    christmas = _observed(date(year, 12, 25))
    if christmas:
        days.add(christmas)
    return days


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


def previous_trading_day(d: date) -> date:
    """Most recent NYSE session strictly before *d*."""
    cur = d - timedelta(days=1)
    while not is_trading_day(cur):
        cur -= timedelta(days=1)
    return cur
