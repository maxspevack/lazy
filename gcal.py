"""Two-way sync between pending tasks and a dedicated Google Calendar.

Lazy is the record. The calendar named "Lazy" (created on first use) is a
view of it that you may also edit. Every reconcile lists the whole calendar,
deleted events included, and merges three ways per task using the stamp
lazy leaves on each event: the task id plus the date and title it last wrote.

  task changed since the stamp      -> the event is rewritten (lazy wins)
  event changed, task did not       -> the task is moved / renamed
  event you deleted on the calendar -> the task is done, if the task still
                                       reads as the event did (lazy marks its
                                       own deletions, so those never count)
  untagged event on the calendar    -> a new task, then the event is stamped
  task done or deleted in lazy      -> the event is deleted

Credentials are the three OAuth values a google-workspace MCP keeps in the
OS keyring (client_id, client_secret, refresh_token) under a configurable
service name. Nothing is stored in this repo or in the gist. urllib only.
Every failure is one stderr line; the task write it rides on still lands.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta

CALENDAR_NAME = 'Lazy'
DEFAULT_KEYRING_SERVICE = 'google-workspace-mcp'
_TOKEN_URL = 'https://oauth2.googleapis.com/token'
_API = 'https://www.googleapis.com/calendar/v3'
_TIMEOUT = 10


class CalendarSyncError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


# ---- credentials ----

def _keyring(service, account):
    if sys.platform == 'darwin':
        cmd = ['security', 'find-generic-password', '-s', service, '-a', account, '-w']
    else:
        cmd = ['secret-tool', 'lookup', 'service', service, 'account', account]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise CalendarSyncError(f"keyring lookup failed: {e}")
    return r.stdout.strip() if r.returncode == 0 else ''


def credentials(service=DEFAULT_KEYRING_SERVICE):
    creds = {k: _keyring(service, k) for k in ('client_id', 'client_secret', 'refresh_token')}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        raise CalendarSyncError(f"no {'/'.join(missing)} in keyring service '{service}'")
    return creds


def access_token(creds):
    data = urllib.parse.urlencode({**creds, 'grant_type': 'refresh_token'}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(_TOKEN_URL, data=data),
                                    timeout=_TIMEOUT) as resp:
            return json.load(resp)['access_token']
    except urllib.error.HTTPError as e:
        raise CalendarSyncError(
            f"token refresh -> HTTP {e.code}: {e.read().decode(errors='replace')[:200]}", e.code)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as e:
        raise CalendarSyncError(f"token refresh -> {e}")


# ---- API ----

class Api:
    """api(method, path, body=None, **query) -> parsed JSON (None for 204)."""

    def __init__(self, token):
        self.token = token

    def __call__(self, method, path, body=None, **params):
        url = _API + path + ('?' + urllib.parse.urlencode(params) if params else '')
        data = json.dumps(body).encode() if body is not None else None
        headers = {'Authorization': 'Bearer ' + self.token, 'Accept': 'application/json'}
        if data is not None:
            headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise CalendarSyncError(
                f"{method} {path} -> HTTP {e.code}: {e.read().decode(errors='replace')[:200]}",
                e.code)
        except (urllib.error.URLError, OSError) as e:
            raise CalendarSyncError(f"{method} {path} -> {e}")
        return json.loads(raw) if raw else None


def find_or_create_calendar(api, name=CALENDAR_NAME):
    # Owner only: a calendar someone shared with you under this name is theirs.
    items = api('GET', '/users/me/calendarList', minAccessRole='owner',
                maxResults=250).get('items', [])
    hits = [c['id'] for c in items if c.get('summary') == name]
    if len(hits) > 1:
        raise CalendarSyncError(f"{len(hits)} calendars named '{name}'; rename all but one")
    if hits:
        return hits[0]
    # The calendar's zone is the zone timed events are listed in; a secondary
    # calendar created without one is UTC, which shifts an evening event to
    # the next day. Inherit the primary's.
    zone = api('GET', '/calendars/primary').get('timeZone')
    return api('POST', '/calendars', {'summary': name, 'timeZone': zone})['id']


# ---- events ----

def _stamp(task):
    return {'lazy_id': str(task['id']), 'lazy_due': task['due_date'],
            'lazy_desc': task['description']}


def _event_for(task):
    due = date.fromisoformat(task['due_date'])
    return {
        'summary': task['description'],
        'description': f"lazy #{task['id']}",
        'start': {'date': due.isoformat()},
        'end': {'date': (due + timedelta(days=1)).isoformat()},   # exclusive end
        'transparency': 'transparent',                            # never "busy"
        'extendedProperties': {'private': _stamp(task)},
    }


def _private(event):
    return (event.get('extendedProperties') or {}).get('private') or {}


def _lazy_id(event):
    try:
        return int(_private(event).get('lazy_id'))
    except (TypeError, ValueError):
        return None


def _event_date(event):
    """YYYY-MM-DD of an all-day event, or the wall-clock day of a timed one
    as the calendar serializes it (in the calendar's own zone). None if absent."""
    start = event.get('start') or {}
    try:
        if start.get('date'):
            return date.fromisoformat(start['date']).isoformat()
        return datetime.fromisoformat(start['dateTime']).date().isoformat()
    except (KeyError, TypeError, ValueError):
        return None


def _cancelled(event):
    return event.get('status') == 'cancelled'


def _adoptable(event):
    """An event you created by hand on the Lazy calendar. One task cannot be a
    series, so recurring events are left alone."""
    return (not _cancelled(event) and _lazy_id(event) is None
            and _event_date(event) is not None
            and 'recurrence' not in event and not event.get('recurringEventId'))


def _list_events(api, cal_id):
    events, page_token = [], None
    while True:
        params = {'maxResults': 2500, 'showDeleted': 'true'}
        if page_token:
            params['pageToken'] = page_token
        page = api('GET', f'/calendars/{cal_id}/events', **params)
        events.extend(page.get('items', []))
        page_token = page.get('nextPageToken')
        if not page_token:
            return events


def _delete(api, cal_id, event_id):
    """One PATCH: cancel the event and mark it as lazy's doing. Cancelling
    by status is what events.delete does for a single event, and the
    tombstone keeps its private properties (receipt 2026-10-31). The marker
    is how the next reconcile tells lazy's own deletion from yours: without
    it, a task that reappears (a replica's late push, a hand edit) would be
    read as "deleted on the calendar" and marked done."""
    try:
        api('PATCH', f'/calendars/{cal_id}/events/{event_id}',
            {'status': 'cancelled', 'extendedProperties': {'private': {'lazy_deleted': '1'}}})
    except CalendarSyncError as e:
        if e.code not in (404, 410):   # already gone is the outcome we wanted
            raise


# ---- reconcile ----

def reconcile(api, cal_id, tasks, add_task):
    """Merge the calendar into `tasks` (mutated in place) and `tasks` into the
    calendar. add_task(description, due_iso) appends a task and returns it.
    Returns counts: events created/updated/deleted, tasks adopted/edited/done."""
    n = dict(created=0, updated=0, deleted=0, adopted=0, edited=0, done=0)
    live, gone = {}, {}
    for ev in _list_events(api, cal_id):
        lid = _lazy_id(ev)
        if lid is None:
            if _adoptable(ev):
                task = add_task(ev.get('summary') or '(untitled)', _event_date(ev))
                try:
                    api('PATCH', f"/calendars/{cal_id}/events/{ev['id']}",
                        {'extendedProperties': {'private': _stamp(task)}})
                except CalendarSyncError:
                    tasks.remove(task)     # unstamped means not adopted; retry next pass
                    raise
                ev['extendedProperties'] = {'private': _stamp(task)}
                live[task['id']] = [ev]    # now ours; the loop below must not recreate it
                n['adopted'] += 1
        elif _cancelled(ev):
            if 'lazy_deleted' not in _private(ev):
                gone[lid] = ev             # deleted by you, not by lazy
        else:
            live.setdefault(lid, []).append(ev)

    pending = {t['id']: t for t in tasks
               if t.get('status') == 'pending' and t.get('due_date')}
    for lid, task in pending.items():
        want = (task['due_date'], task['description'])
        events = live.get(lid)
        if not events:
            tomb = _private(gone.get(lid, {}))
            if (tomb.get('lazy_due'), tomb.get('lazy_desc')) == want:
                # You deleted the event of this task as it stands: done.
                # A tombstone that reads differently is an earlier bearer of
                # the id (ids are reused after `lazy rm`) or predates an edit
                # lazy made since; either way the task gets a fresh event.
                task['status'] = 'done'
                n['done'] += 1
            else:
                api('POST', f'/calendars/{cal_id}/events', _event_for(task))
                n['created'] += 1
            continue
        ev, dupes = events[0], events[1:]
        priv = _private(ev)
        base = (priv.get('lazy_due'), priv.get('lazy_desc'))
        now = (_event_date(ev), ev.get('summary') or '')
        if None in base or want != base:
            # Lazy changed since it last wrote (or never stamped): lazy wins.
            # PUT, not PATCH: a hand-converted timed event comes back all-day,
            # and PATCH merges start/end instead of replacing them.
            api('PUT', f"/calendars/{cal_id}/events/{ev['id']}", _event_for(task))
            n['updated'] += 1
        elif now[0] is not None and now != base:
            # You edited the event: the task follows, and only the stamp moves,
            # so a timed event stays timed. An event with no start is left alone.
            task['due_date'], task['description'] = now[0], now[1] or task['description']
            api('PATCH', f"/calendars/{cal_id}/events/{ev['id']}",
                {'extendedProperties': {'private': _stamp(task)}})
            n['edited'] += 1
        for dup in dupes:                  # two machines raced to create; keep one
            _delete(api, cal_id, dup['id'])
            n['deleted'] += 1
    # Done or removed in lazy, or a task another machine added whose push has
    # not reached this file yet. The marker _delete leaves makes the second
    # case harmless: once the task arrives, its event is simply recreated.
    for lid, events in live.items():
        if lid not in pending:
            for ev in events:
                _delete(api, cal_id, ev['id'])
                n['deleted'] += 1
    return n


def _cached_calendar(api, cache_path, tasks, add_task):
    """Reconcile against the calendar id remembered in cache_path, looking it
    up (one calendarList call) only when there is no cache or the cached
    calendar is gone (Google answers 404 for a deleted calendar; receipt
    2026-10-31). The id is per clone, next to the pull sentinel; it is not a
    credential. With a cached id the two-calendars-named-Lazy check does not
    run, which is fine: the id itself is unambiguous."""
    cal_id = None
    if cache_path:
        try:
            with open(cache_path) as f:
                cal_id = f.read().strip() or None
        except OSError:
            pass
    if cal_id:
        try:
            return reconcile(api, cal_id, tasks, add_task)
        except CalendarSyncError as e:
            if e.code != 404:
                raise
    cal_id = find_or_create_calendar(api)
    if cache_path:
        try:
            with open(cache_path, 'w') as f:
                f.write(cal_id + '\n')
        except OSError:
            pass
    return reconcile(api, cal_id, tasks, add_task)


def sync(tasks, add_task, service=DEFAULT_KEYRING_SERVICE, warn=None, cache_path=None):
    """Reconcile and report. Never raises: the task write this rides on must
    land whatever the calendar does. Every reconcile re-derives the whole
    diff, so a skipped one heals on the next. Returns the counts, or None."""
    if warn is None:
        warn = lambda m: sys.stderr.write(f"lazy: calendar sync skipped: {m}\n")
    try:
        api = Api(access_token(credentials(service)))
        return _cached_calendar(api, cache_path, tasks, add_task)
    except CalendarSyncError as e:
        warn(str(e))
    except Exception as e:             # a bug here must not break `lazy add`
        warn(f"{type(e).__name__}: {e}")
    return None
