"""One-way mirror of pending tasks onto a dedicated Google Calendar.

Lazy is the source of truth. After every write, the pending set is
reconciled against a calendar named "Lazy" (created on first use): one
all-day event per pending task on its due date, tagged with the task id in a
private extended property. Done, deleted, moved, or renamed tasks have their
event deleted, moved, or renamed on the next reconcile. Events on that
calendar without a tag are left alone; other calendars are never touched.

Credentials are the three OAuth values a google-workspace MCP already keeps
in the platform secret store (client_id, client_secret, refresh_token) under
a configurable service name. No third-party packages: urllib and the OS
keyring CLI. Every failure is one stderr line; the task write stands.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

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
    items = api('GET', '/users/me/calendarList', minAccessRole='writer',
                maxResults=250).get('items', [])
    hits = [c['id'] for c in items if c.get('summary') == name]
    if len(hits) > 1:
        raise CalendarSyncError(f"{len(hits)} calendars named '{name}'; rename all but one")
    if hits:
        return hits[0]
    return api('POST', '/calendars', {'summary': name})['id']


# ---- reconcile ----

def _event_for(task):
    due = date.fromisoformat(task['due_date'])
    return {
        'summary': task['description'],
        'description': f"lazy #{task['id']}",
        'start': {'date': due.isoformat()},
        'end': {'date': (due + timedelta(days=1)).isoformat()},   # exclusive end
        'transparency': 'transparent',                            # never "busy"
        'extendedProperties': {'private': {'lazy_id': str(task['id'])}},
    }


def _lazy_id(event):
    try:
        return int(event.get('extendedProperties', {}).get('private', {}).get('lazy_id'))
    except (TypeError, ValueError):
        return None


def _list_events(api, cal_id):
    events, page_token = [], None
    while True:
        params = {'maxResults': 2500, 'showDeleted': 'false'}
        if page_token:
            params['pageToken'] = page_token
        page = api('GET', f'/calendars/{cal_id}/events', **params)
        events.extend(page.get('items', []))
        page_token = page.get('nextPageToken')
        if not page_token:
            return events


def _delete(api, cal_id, event_id):
    try:
        api('DELETE', f'/calendars/{cal_id}/events/{event_id}')
    except CalendarSyncError as e:
        if e.code not in (404, 410):   # already gone is the outcome we wanted
            raise


def reconcile(api, cal_id, tasks):
    """Make the calendar match the pending tasks. Returns (created, updated, deleted)."""
    pending = {t['id']: t for t in tasks
               if t.get('status') == 'pending' and t.get('due_date')}
    current = {}
    for ev in _list_events(api, cal_id):
        lid = _lazy_id(ev)
        if lid is not None:            # untagged events are not ours; never touched
            current.setdefault(lid, []).append(ev)

    created = updated = deleted = 0
    for lid, task in pending.items():
        want = _event_for(task)
        events = current.get(lid, [])
        if not events:
            api('POST', f'/calendars/{cal_id}/events', want)
            created += 1
            continue
        keep, dupes = events[0], events[1:]
        if any(keep.get(k) != want[k] for k in ('summary', 'start', 'end')):
            # PUT, not PATCH: a hand-converted timed event must come back
            # all-day, and PATCH merges start/end instead of replacing them.
            api('PUT', f"/calendars/{cal_id}/events/{keep['id']}", want)
            updated += 1
        for ev in dupes:               # a run that died between insert and exit left two
            _delete(api, cal_id, ev['id'])
            deleted += 1
    for lid, events in current.items():
        if lid not in pending:
            for ev in events:
                _delete(api, cal_id, ev['id'])
                deleted += 1
    return created, updated, deleted


def sync(tasks, service=DEFAULT_KEYRING_SERVICE, warn=None):
    """Reconcile and report. Never raises: the task write this follows is
    already committed, and a calendar problem must not undo it. Every full
    reconcile re-derives the whole diff, so a skipped sync heals on the next
    write. Returns (created, updated, deleted), or None when skipped."""
    if warn is None:
        warn = lambda m: sys.stderr.write(f"lazy: calendar sync skipped: {m}\n")
    try:
        api = Api(access_token(credentials(service)))
        return reconcile(api, find_or_create_calendar(api), tasks)
    except CalendarSyncError as e:
        warn(str(e))
    except Exception as e:             # a bug here must not break `lazy add`
        warn(f"{type(e).__name__}: {e}")
    return None
