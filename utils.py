from datetime import date, timedelta, datetime
import re
import calendar
import json
import os

_config_cache = None

def load_config():
    """
    Loads the configuration from 'config.json' with in-memory caching.
    
    This function reads the JSON configuration file from the same directory as this script.
    It caches the result in a global variable `_config_cache` to prevent repeated disk I/O
    during high-frequency calls (like inside a parsing loop).
    
    Returns:
        dict: The configuration dictionary. Returns an empty dict if the file is missing or invalid.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache
        
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, 'config.json')
    try:
        with open(config_path, 'r') as f:
            _config_cache = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _config_cache = {}
        
    return _config_cache

def parse_date(date_str):
    """
    Parses a natural language date string into a datetime.date object.
    
    This function handles a wide variety of date formats optimized for a "lazy" workflow.
    It includes custom logic for handling "next" keywords to match intuitive procrastination patterns.

    Supported Formats:
    1. Keywords: 'today', 'tomorrow' (tmw), 'yesterday'
    2. Relative Offsets: '+1' (days), '+1w' (weeks), '+1m' (months), '+1y' (years)
    3. Shorthand Offsets: '2w', '3m'
    4. Special Phrases: 'soon' (+3d), 'later' (+7d), 'someday' (+30d), 'weekend' (Next Sat)
    5. Weekdays: 'mon', 'tue', etc. (Finds the *next* occurrence)
    6. "Lazy Next": 'next fri' (Skips the current week's Friday if it exists, jumping to next week)
    7. Explicit Dates: 'YYYY-MM-DD', 'MM-DD', 'M/D'

    Args:
        date_str (str): The date string to parse (e.g., "next fri", "2025-01-01").
                        If None or empty, returns today's date.

    Returns:
        datetime.date: The parsed date object.

    Raises:
        ValueError: If the date string cannot be parsed.
    """
    if not date_str:
        return date.today()

    config = load_config()
    # date_logic is hardcoded to 'lazy_next' per project specifications.

    today = date.today()
    lower_str = date_str.lower().strip()

    # 1. Keywords
    if lower_str in ('today', 'tod'):
        return today
    if lower_str in ('tomorrow', 'tmw', 'tom'):
        return today + timedelta(days=1)
    
    # 2. Relative offsets (+1, +7)
    if lower_str.startswith('+'):
        # ... (same as before) ...
        try:
            # Check for suffixes
            if lower_str.endswith('w'):
                weeks = int(lower_str[1:-1])
                return today + timedelta(weeks=weeks)
            elif lower_str.endswith('m'):
                months = int(lower_str[1:-1])
                # Simple month adder: same day next month
                new_month = today.month + months
                year_add = (new_month - 1) // 12
                new_month = (new_month - 1) % 12 + 1
                new_year = today.year + year_add
                _, max_days = calendar.monthrange(new_year, new_month)
                new_day = min(today.day, max_days)
                return date(new_year, new_month, new_day)
            elif lower_str.endswith('y'):
                years = int(lower_str[1:-1])
                try:
                    return today.replace(year=today.year + years)
                except ValueError:
                    return today + timedelta(days=365 * years) 
            else:
                days = int(lower_str[1:])
                return today + timedelta(days=days)
        except ValueError:
            pass
    
    # 2b. Shorthand w/m/y without plus
    if lower_str[-1] in ('w', 'm', 'y') and lower_str[:-1].isdigit():
        val = int(lower_str[:-1])
        if lower_str.endswith('w'):
            return today + timedelta(weeks=val)
        elif lower_str.endswith('m'):
            new_month = today.month + val
            year_add = (new_month - 1) // 12
            new_month = (new_month - 1) % 12 + 1
            new_year = today.year + year_add
            _, max_days = calendar.monthrange(new_year, new_month)
            new_day = min(today.day, max_days)
            return date(new_year, new_month, new_day)
        elif lower_str.endswith('y'):
             try:
                return today.replace(year=today.year + val)
             except ValueError:
                return date(today.year + val, 2, 28)

    # 2c. Special phrases
    if lower_str == 'soon':
        return today + timedelta(days=3)
    if lower_str == 'later':
        return today + timedelta(days=7)
    if lower_str in ('someday', 'eventually'):
        return today + timedelta(days=30)
    if lower_str == 'weekend' or lower_str == 'this weekend':
        # Next Saturday
        current = today.weekday()
        # Sat = 5
        days_until_sat = 5 - current
        if days_until_sat <= 0:
            days_until_sat += 7
        return today + timedelta(days=days_until_sat)

    if lower_str == 'next weekend':
        # Saturday of next week (or skip one Saturday)
        # First find "this weekend"
        current = today.weekday()
        days_until_sat = 5 - current
        if days_until_sat <= 0:
            days_until_sat += 7
        # Then add 7 days
        return today + timedelta(days=days_until_sat + 7)

    if lower_str == 'next week':
        # Max's Logic: "Next Week" skips the immediate week if we are close to it?
        # User said Sun -> "Next Week" = 8 days (Monday of week after next).
        if today.weekday() == 6: # Sunday
             # If Sunday, "Next Week" starts 8 days later (Mon)
             return today + timedelta(days=8)
        return today + timedelta(weeks=1)

    if lower_str == 'next month':
        if today.month == 12:
            return date(today.year + 1, 1, 1)
        else:
            return date(today.year, today.month + 1, 1)
    if lower_str == 'next year':
        return date(today.year + 1, 1, 1)
        
    if lower_str == 'eow': # End of week -> Next Friday
        current = today.weekday()
        days_until_fri = (4 - current)
        if days_until_fri <= 0: 
            days_until_fri += 7
        return today + timedelta(days=days_until_fri)
        
    if lower_str == 'eom': 
        _, max_days = calendar.monthrange(today.year, today.month)
        return date(today.year, today.month, max_days)
        
    if lower_str == 'eoy': 
        return date(today.year, 12, 31)

    # 3. Days of the week
    is_next_keyword = False
    if lower_str.startswith('next '):
        is_next_keyword = True
        lower_str = lower_str[5:]
        
    weekdays = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
    for idx, day in enumerate(weekdays):
        if lower_str.startswith(day):
            current_weekday = today.weekday()
            days_ahead = idx - current_weekday
            
            # Basic "Next Occurrence" logic
            if days_ahead <= 0:
                days_ahead += 7
            elif days_ahead == 0 and not is_next_keyword:
                 days_ahead += 7

            # "LAZY NEXT" LOGIC (Max's Preference) - UNCONDITIONAL
            if is_next_keyword:
                
                # If Today is Sunday (6), and we ask for "Next Mon" (0):
                # Standard days_ahead would be 1 (Mon is tomorrow).
                # Max wants 8.
                if current_weekday == 6:
                    days_ahead += 7
                
                # General Rule: If the target day is in the *Current* ISO Week (Mon-Sun),
                # and we said "Next", we skip it.
                elif idx > current_weekday:
                     days_ahead += 7
            
            return today + timedelta(days=days_ahead)

    # 4. Specific dates (YYYY-MM-DD, M/D)
    formats = [
        '%Y-%m-%d', # 2025-12-17
        '%m-%d',    # 12-17 (Assumes current year)
        '%m/%d',    # 12/17
        '%d.%m'     # 17.12
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            # If year is missing (1900), replace with current year
            if dt.year == 1900:
                dt = dt.replace(year=today.year)
                # If that date has already passed, maybe they mean next year?
                # Let's keep it simple for now and assume current year.
            return dt.date()
        except ValueError:
            continue

    # 5. Fallback/Error
    raise ValueError(f"Could not parse date: '{date_str}'")
