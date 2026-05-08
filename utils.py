import calendar
import json
import os
import random
import re
from datetime import date, datetime, timedelta

_config_cache = None

def load_config():
    """Read config.json once per process. Returns {} if missing or malformed."""
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(base_dir, 'config.json')) as f:
            _config_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _config_cache = {}
    return _config_cache


def get_vibe_echo(description, date_obj):
    """Return a random vibe-aligned message for a freshly-added task."""
    today = date.today()
    if date_obj == today:
        date_str = "today"
    elif date_obj == today + timedelta(days=1):
        date_str = "tomorrow"
    else:
        date_str = date_obj.strftime("%a, %b %d")
    config = load_config()
    messages = config.get('add_echo_messages', [f"Added '{description}' for {date_str}."])
    return random.choice(messages).replace("{description}", description).replace("{date}", date_str)


def _add_months(d, months):
    new_month = d.month + months
    year_add = (new_month - 1) // 12
    new_month = (new_month - 1) % 12 + 1
    new_year = d.year + year_add
    _, max_days = calendar.monthrange(new_year, new_month)
    return date(new_year, new_month, min(d.day, max_days))


def _add_years(d, years):
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return date(d.year + years, 2, 28)


_KEYWORDS = {
    'today': 0, 'tod': 0, 'yesterday': -1,
    'tomorrow': 1, 'tmw': 1, 'tom': 1,
    'soon': 3, 'later': 7, 'someday': 30, 'eventually': 30,
}

_MONTHS = {
    'jan': 1, 'january': 1, 'feb': 2, 'february': 2,
    'mar': 3, 'march': 3, 'apr': 4, 'april': 4,
    'may': 5, 'jun': 6, 'june': 6, 'jul': 7, 'july': 7,
    'aug': 8, 'august': 8, 'sep': 9, 'september': 9,
    'oct': 10, 'october': 10, 'nov': 11, 'november': 11,
    'dec': 12, 'december': 12,
}

_WEEKDAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']

_OFFSET_RE = re.compile(r'^\+?(\d+)([dwmy]?)$')
_FUZZY_RE = re.compile(r'^(?:in\s+)?(\d+)\s+(day|week|month|year)s?$')
_EXPLICIT_FORMATS = ['%Y-%m-%d', '%m-%d', '%m/%d', '%d.%m']


def parse_date(date_str, today=None):
    """Parse a natural-language date string into a date.

    Supports keywords (today/tmw/yesterday/soon/later/someday/eventually),
    offsets (+1, 2w, 3m, 1y), fuzzy phrases (in 3 days, 5 weeks),
    weekend/week/month/year navigators (eow/eom/eoy, weekend, next week...),
    weekdays (mon/tue/.../sun, optionally prefixed with 'next' for the
    "Lazy Next" skip-this-week behavior), month names (jan/january/...),
    and explicit dates (YYYY-MM-DD, MM-DD, M/D, D.M).

    today is the reference date; defaults to date.today(). Exposed for tests
    so behavior at specific weekdays can be verified deterministically.
    """
    if today is None:
        today = date.today()
    if not date_str:
        return today

    s = date_str.lower().strip()

    if s in _KEYWORDS:
        return today + timedelta(days=_KEYWORDS[s])

    if s in ('weekend', 'this weekend'):
        return today + timedelta(days=((5 - today.weekday()) % 7) or 7)
    if s == 'next weekend':
        return today + timedelta(days=(((5 - today.weekday()) % 7) or 7) + 7)
    if s == 'next week':
        return today + timedelta(days=8 if today.weekday() == 6 else 7)
    if s == 'next month':
        return _add_months(date(today.year, today.month, 1), 1)
    if s == 'next year':
        return date(today.year + 1, 1, 1)
    if s == 'eow':
        return today + timedelta(days=((4 - today.weekday()) % 7) or 7)
    if s == 'eom':
        _, last = calendar.monthrange(today.year, today.month)
        return date(today.year, today.month, last)
    if s == 'eoy':
        return date(today.year, 12, 31)

    m = _FUZZY_RE.match(s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit == 'day':   return today + timedelta(days=n)
        if unit == 'week':  return today + timedelta(weeks=n)
        if unit == 'month': return _add_months(today, n)
        if unit == 'year':  return _add_years(today, n)

    m = _OFFSET_RE.match(s)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        if unit in ('', 'd'): return today + timedelta(days=n)
        if unit == 'w':       return today + timedelta(weeks=n)
        if unit == 'm':       return _add_months(today, n)
        if unit == 'y':       return _add_years(today, n)

    if s in _MONTHS:
        target_month = _MONTHS[s]
        target_year = today.year if target_month > today.month else today.year + 1
        return date(target_year, target_month, 1)

    is_next = s.startswith('next ')
    bare = s[5:] if is_next else s
    for idx, day in enumerate(_WEEKDAYS):
        if bare.startswith(day):
            # Plain '<day>' = next occurrence (1-7 days ahead).
            # 'next <day>' = skip the upcoming one, get the week after.
            days_ahead = (idx - today.weekday()) % 7 or 7
            if is_next:
                days_ahead += 7
            return today + timedelta(days=days_ahead)

    for fmt in _EXPLICIT_FORMATS:
        try:
            if '%Y' not in fmt:
                dt = datetime.strptime(f"{today.year}-{date_str}", f"%Y-{fmt}")
            else:
                dt = datetime.strptime(date_str, fmt)
            return dt.date()
        except ValueError:
            continue

    raise ValueError(f"Could not parse date: '{date_str}'")
