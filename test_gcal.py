"""Calendar sync: the two-way reconcile against a fake Calendar API, every
store mutation driven through the real sync path, and the store hook. No
network. The live path gets a hand-run receipt against a throwaway event."""

import os
import shutil
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gcal
import store as store_mod
from store import Store
from tests_common import setup_repo as _setup_repo, read_tasks


def task(id_, desc, due, status='pending'):
    return {'id': id_, 'description': desc, 'due_date': due, 'status': status}


def _next_day(iso):
    return (date.fromisoformat(iso) + timedelta(days=1)).isoformat()


class FakeApi:
    """Enough of Calendar v3 for reconcile(). Deleting keeps the event in the
    listing as cancelled, as Google does; PATCH merges; PUT replaces."""

    def __init__(self, calendars=None, events=(), page_size=None):
        self.calendars = calendars if calendars is not None else [{'id': 'cal1', 'summary': 'Lazy'}]
        self.events = {e['id']: e for e in events}
        self.calls = []
        self.page_size = page_size
        self._n = 0

    def __call__(self, method, path, body=None, **params):
        self.calls.append((method, path))
        if path == '/users/me/calendarList':
            return {'items': self.calendars}
        if path == '/calendars/primary' and method == 'GET':
            return {'id': 'primary', 'timeZone': 'America/Los_Angeles'}
        if path == '/calendars' and method == 'POST':
            self.calendars.append(dict(body, id='newcal'))
            return {'id': 'newcal'}
        if path.startswith('/calendars/') and path.split('/')[2] not in {c['id'] for c in self.calendars}:
            raise gcal.CalendarSyncError('calendar not found', 404)
        if path.endswith('/events') and method == 'GET':
            items = list(self.events.values())
            if params.get('showDeleted') != 'true':
                items = [e for e in items if e.get('status') != 'cancelled']
            if self.page_size:
                start = int(params.get('pageToken', 0))
                page = {'items': items[start:start + self.page_size]}
                if start + self.page_size < len(items):
                    page['nextPageToken'] = str(start + self.page_size)
                return page
            return {'items': items}
        if path.endswith('/events') and method == 'POST':
            self._n += 1
            ev = dict(body, id=f'ev{self._n}', status='confirmed')
            self.events[ev['id']] = ev
            return ev
        event_id = path.rsplit('/', 1)[1]
        ev = self.events.get(event_id)
        if ev is None or ev.get('status') == 'cancelled':
            raise gcal.CalendarSyncError('gone', 410)
        if method == 'PUT':
            self.events[event_id] = dict(body, id=event_id, status='confirmed')
            return self.events[event_id]
        if method == 'PATCH':
            for k, v in body.items():
                if k == 'extendedProperties':
                    ev.setdefault('extendedProperties', {}).setdefault('private', {}).update(v['private'])
                else:
                    ev[k] = v
            return ev
        if method == 'DELETE':
            ev['status'] = 'cancelled'
            return None
        raise AssertionError(f"unexpected {method} {path}")

    def mutations(self):
        return [c for c in self.calls if c[0] != 'GET']

    def live(self):
        return {e['id']: e for e in self.events.values() if e.get('status') != 'cancelled'}

    def add_manual(self, summary, start, **extra):
        """What a human does in the Google Calendar UI. An all-day event's
        end is the next day, exclusive, as Google stores it."""
        self._n += 1
        end = {'date': _next_day(start['date'])} if 'date' in start else start
        ev = {'id': f'manual{self._n}', 'summary': summary, 'start': start,
              'end': end, 'status': 'confirmed', **extra}
        self.events[ev['id']] = ev
        return ev


def event_of(api, lid):
    return next(e for e in api.live().values()
                if e['extendedProperties']['private']['lazy_id'] == str(lid))


def reconcile(api, tasks):
    """reconcile() with the simplest possible add_task."""
    def add(desc, due):
        t = task(max([t['id'] for t in tasks], default=0) + 1, desc, due)
        tasks.append(t)
        return t
    return gcal.reconcile(api, 'cal1', tasks, add)


class TestOutbound(unittest.TestCase):
    def test_pending_tasks_become_stamped_all_day_events(self):
        api = FakeApi()
        n = reconcile(api, [task(1, 'Call the plumber', '2026-11-03'),
                            task(2, 'Old thing', '2026-10-01', status='done')])
        self.assertEqual(n['created'], 1)
        (ev,) = api.events.values()
        self.assertEqual(ev['summary'], 'Call the plumber')
        self.assertEqual((ev['start'], ev['end']), ({'date': '2026-11-03'}, {'date': '2026-11-04'}))
        self.assertEqual(ev['extendedProperties']['private'],
                         {'lazy_id': '1', 'lazy_due': '2026-11-03', 'lazy_desc': 'Call the plumber'})
        self.assertEqual(ev['transparency'], 'transparent')

    def test_second_pass_is_read_only(self):
        api = FakeApi()
        tasks = [task(1, 'Call the plumber', '2026-11-03'), task(2, 'Fix the gate', '2027-01-01')]
        reconcile(api, tasks)
        api.calls.clear()
        self.assertFalse(any(reconcile(api, tasks).values()))
        self.assertEqual(api.mutations(), [])

    def test_task_edit_rewrites_the_event(self):
        api = FakeApi()
        reconcile(api, [task(1, 'Call the plumber', '2026-11-03')])
        api.calls.clear()
        n = reconcile(api, [task(1, 'Call the plumber (cell)', '2026-11-05')])
        self.assertEqual(n['updated'], 1)
        self.assertEqual([c[0] for c in api.mutations()], ['PUT'])
        (ev,) = api.live().values()
        self.assertEqual((ev['summary'], ev['start']['date'], ev['end']['date']),
                         ('Call the plumber (cell)', '2026-11-05', '2026-11-06'))
        self.assertEqual(ev['extendedProperties']['private']['lazy_due'], '2026-11-05')

    def test_done_and_removed_tasks_lose_their_events_once(self):
        api = FakeApi()
        reconcile(api, [task(1, 'A', '2026-11-03'), task(2, 'B', '2026-11-04')])
        api.calls.clear()
        n = reconcile(api, [task(1, 'A', '2026-11-03', status='done')])
        self.assertEqual(n['deleted'], 2)
        self.assertEqual(api.live(), {})
        self.assertEqual([c[0] for c in api.mutations()], ['PATCH', 'PATCH'], "one call per tombstone")
        self.assertTrue(all(e['status'] == 'cancelled' and e['extendedProperties']['private']['lazy_deleted'] == '1'
                            for e in api.events.values()))
        api.calls.clear()
        reconcile(api, [task(1, 'A', '2026-11-03', status='done')])
        self.assertEqual(api.mutations(), [], "a cancelled event must not be deleted again")

    def test_unstamped_event_from_an_older_lazy_is_stamped_by_a_put(self):
        old = {'id': 'old', 'summary': 'Legacy', 'start': {'date': '2026-11-03'},
               'end': {'date': '2026-11-04'}, 'status': 'confirmed',
               'extendedProperties': {'private': {'lazy_id': '9'}}}
        api = FakeApi(events=[old])
        n = reconcile(api, [task(9, 'Legacy', '2026-11-03')])
        self.assertEqual((n['updated'], n['edited']), (1, 0))
        self.assertEqual(api.events['old']['extendedProperties']['private']['lazy_due'], '2026-11-03')

    def test_duplicate_live_events_collapse_to_one(self):
        t = task(7, 'Twice', '2026-11-03')
        dup = lambda i: dict(gcal._event_for(t), id=f'd{i}', status='confirmed')
        api = FakeApi(events=[dup(1), dup(2)])
        self.assertEqual(reconcile(api, [t])['deleted'], 1)
        self.assertEqual(list(api.live()), ['d1'])

    def test_listing_follows_every_page(self):
        api = FakeApi(page_size=1)
        tasks = [task(1, 'A', '2026-11-03'), task(2, 'B', '2026-11-04'), task(3, 'C', '2026-11-05')]
        reconcile(api, tasks)
        api.calls.clear()
        self.assertFalse(any(reconcile(api, tasks).values()))
        self.assertEqual(sum(1 for c in api.calls if c[1].endswith('/events')), 3, "three pages read")
        self.assertEqual(api.mutations(), [])

    def test_lazys_own_deletion_is_never_read_as_yours(self):
        api = FakeApi()
        t = task(7, 'Reopened later', '2026-11-03')
        reconcile(api, [t])
        reconcile(api, [dict(t, status='done')])              # lazy deletes; tombstone carries lazy_deleted
        self.assertEqual(api.events[event_id := next(iter(api.events))]['extendedProperties']['private']['lazy_deleted'], '1')
        again = dict(t)                                          # hand edit or late replica: pending again
        n = reconcile(api, [again])
        self.assertEqual((again['status'], n['done'], n['created']), ('pending', 0, 1))

    def test_removing_the_newest_task_and_reusing_its_id_is_clean(self):
        # lazy mints ids as max+1, so a removed newest task's id comes back.
        api = FakeApi()
        reconcile(api, [task(1, 'Keep', '2026-11-03'), task(2, 'Removed', '2026-11-04')])
        self.assertEqual(reconcile(api, [task(1, 'Keep', '2026-11-03')])['deleted'], 1)
        self.assertEqual(len(api.live()), 1, "the removed task's event goes at once")
        for ev in list(api.events.values()):                    # you tidy the tombstone's twin by hand
            if ev.get('status') == 'cancelled':
                api.events.pop(ev['id'])
        reborn = task(2, 'New task, same id', '2026-11-20')
        n = reconcile(api, [task(1, 'Keep', '2026-11-03'), reborn])
        self.assertEqual((reborn['status'], n['created'], n['done']), ('pending', 1, 0))

    def test_an_event_with_no_start_leaves_the_task_alone(self):
        api = FakeApi()
        t = task(1, 'X', '2026-11-03')
        reconcile(api, [t])
        ev = next(iter(api.live().values()))
        ev.pop('start'), ev.pop('end')
        self.assertFalse(any(reconcile(api, [t]).values()))
        self.assertEqual(t['due_date'], '2026-11-03')

    def test_delete_of_an_already_gone_event_is_not_an_error(self):
        t = task(3, 'Ghost', '2026-11-03')
        api = FakeApi(events=[dict(gcal._event_for(t), id='g1', status='confirmed')])
        real = api.__call__
        def racing(method, path, body=None, **params):
            if method == 'GET' and path.endswith('/events'):
                page = real(method, path, body, **params)
                api.events.clear()           # someone else emptied the calendar mid-run
                return page
            return real(method, path, body, **params)
        self.assertEqual(reconcile(racing, [task(3, 'Ghost', '2026-11-03', status='done')])['deleted'], 1)


class TestInbound(unittest.TestCase):
    def setUp(self):
        self.api = FakeApi()
        self.tasks = [task(1, 'Call the plumber', '2026-11-03'), task(2, 'Fix the gate', '2027-01-01')]
        reconcile(self.api, self.tasks)
        self.api.calls.clear()

    def event(self, lid):
        return event_of(self.api, lid)

    def test_moving_an_event_moves_the_task(self):
        ev = self.event(1)
        ev['start'], ev['end'] = {'date': '2026-11-10'}, {'date': '2026-11-11'}
        n = reconcile(self.api, self.tasks)
        self.assertEqual((n['edited'], n['updated']), (1, 0))
        self.assertEqual(self.tasks[0]['due_date'], '2026-11-10')
        self.assertEqual([c[0] for c in self.api.mutations()], ['PATCH'])
        self.assertEqual(ev['extendedProperties']['private']['lazy_due'], '2026-11-10')
        self.api.calls.clear()
        reconcile(self.api, self.tasks)
        self.assertEqual(self.api.mutations(), [], "settled after one pass")

    def test_renaming_an_event_renames_the_task(self):
        self.event(2)['summary'] = 'Fix the back gate'
        self.assertEqual(reconcile(self.api, self.tasks)['edited'], 1)
        self.assertEqual(self.tasks[1]['description'], 'Fix the back gate')

    def test_converting_to_a_timed_event_keeps_the_time_and_moves_the_task(self):
        ev = self.event(1)
        ev['start'] = {'dateTime': '2026-11-12T15:00:00-08:00'}
        ev['end'] = {'dateTime': '2026-11-12T15:30:00-08:00'}
        reconcile(self.api, self.tasks)
        self.assertEqual(self.tasks[0]['due_date'], '2026-11-12')
        self.assertIn('dateTime', ev['start'], "inbound edits never rewrite the event body")

    def test_deleting_an_event_marks_the_task_done_and_stays_done(self):
        self.api('DELETE', '/calendars/cal1/events/' + self.event(1)['id'])
        self.api.calls.clear()
        n = reconcile(self.api, self.tasks)
        self.assertEqual((n['done'], n['created'], n['deleted']), (1, 0, 0))
        self.assertEqual(self.tasks[0]['status'], 'done')
        self.assertEqual(self.api.mutations(), [])
        reconcile(self.api, self.tasks)
        self.assertEqual(len(self.api.live()), 1, "the done task is not recreated")

    def test_a_task_edited_in_lazy_outlives_a_concurrent_event_deletion(self):
        self.api('DELETE', '/calendars/cal1/events/' + self.event(1)['id'])
        self.tasks[0]['due_date'] = '2026-12-25'
        n = reconcile(self.api, self.tasks)
        self.assertEqual((self.tasks[0]['status'], n['done'], n['created']), ('pending', 0, 1))
        self.assertEqual(self.event(1)['start']['date'], '2026-12-25')

    def test_a_reused_id_is_not_completed_by_its_predecessors_tombstone(self):
        # Observed live 2026-10-31: task 110 removed, its hand-deleted tombstone
        # still listed, `lazy a` minted 110 again, and the add came out done.
        self.api('DELETE', '/calendars/cal1/events/' + self.event(2)['id'])   # you delete it
        del self.tasks[1]                                                      # lazy rm 2
        reborn = task(2, 'Something new', '2026-12-01')
        self.tasks.append(reborn)
        n = reconcile(self.api, self.tasks)
        self.assertEqual((reborn['status'], n['done'], n['created']), ('pending', 0, 1))

    def test_both_changed_lazy_wins(self):
        ev = self.event(1)
        ev['start'], ev['end'] = {'date': '2026-11-10'}, {'date': '2026-11-11'}
        self.tasks[0]['due_date'] = '2026-11-20'
        n = reconcile(self.api, self.tasks)
        self.assertEqual((n['updated'], n['edited']), (1, 0))
        self.assertEqual(self.tasks[0]['due_date'], '2026-11-20')
        self.assertEqual(self.api.live()[ev['id']]['start']['date'], '2026-11-20')

    def test_a_hand_made_event_becomes_a_task_and_is_stamped(self):
        ev = self.api.add_manual('Buy stamps', {'date': '2026-11-15'})
        n = reconcile(self.api, self.tasks)
        self.assertEqual(n['adopted'], 1)
        new = self.tasks[-1]
        self.assertEqual((new['id'], new['description'], new['due_date'], new['status']),
                         (3, 'Buy stamps', '2026-11-15', 'pending'))
        self.assertEqual(ev['extendedProperties']['private'],
                         {'lazy_id': '3', 'lazy_due': '2026-11-15', 'lazy_desc': 'Buy stamps'})
        self.assertEqual([c[0] for c in self.api.mutations()], ['PATCH'])
        self.api.calls.clear()
        reconcile(self.api, self.tasks)
        self.assertEqual(self.api.mutations(), [], "adopted once, then settled")

    def test_hand_made_timed_and_untitled_events(self):
        self.api.add_manual(None, {'dateTime': '2026-11-16T09:00:00-08:00'})
        reconcile(self.api, self.tasks)
        self.assertEqual((self.tasks[-1]['description'], self.tasks[-1]['due_date']),
                         ('(untitled)', '2026-11-16'))

    def test_a_failed_stamp_leaves_no_half_adopted_task(self):
        self.api.add_manual('Buy stamps', {'date': '2026-11-15'})
        real = self.api.__call__
        def flaky(method, path, body=None, **params):
            if method == 'PATCH':
                raise gcal.CalendarSyncError('PATCH -> HTTP 503', 503)
            return real(method, path, body, **params)
        for _ in range(3):
            with self.assertRaises(gcal.CalendarSyncError):
                reconcile(flaky, self.tasks)
        self.assertEqual(len(self.tasks), 2, "no phantom task per pass")
        self.assertEqual(reconcile(self.api, self.tasks)['adopted'], 1, "adopted once the stamp lands")

    def test_recurring_and_cancelled_hand_made_events_are_ignored(self):
        self.api.add_manual('Weekly', {'date': '2026-11-16'}, recurrence=['RRULE:FREQ=WEEKLY'])
        self.api.add_manual('Instance', {'date': '2026-11-23'}, recurringEventId='x')
        self.api.add_manual('Trashed', {'date': '2026-11-17'}, status='cancelled')
        self.assertEqual(reconcile(self.api, self.tasks)['adopted'], 0)
        self.assertEqual(len(self.tasks), 2)


class TestCalendarLookup(unittest.TestCase):
    def test_existing_calendar_is_reused(self):
        api = FakeApi()
        self.assertEqual(gcal.find_or_create_calendar(api), 'cal1')
        self.assertEqual(api.mutations(), [])

    def test_missing_calendar_is_created_in_the_primary_zone(self):
        api = FakeApi(calendars=[{'id': 'p', 'summary': 'someone@example.com'}])
        self.assertEqual(gcal.find_or_create_calendar(api), 'newcal')
        self.assertEqual(api.mutations(), [('POST', '/calendars')])
        self.assertEqual(api.calendars[-1]['timeZone'], 'America/Los_Angeles')

    def test_two_calendars_with_the_name_refuse(self):
        api = FakeApi(calendars=[{'id': 'a', 'summary': 'Lazy'}, {'id': 'b', 'summary': 'Lazy'}])
        with self.assertRaises(gcal.CalendarSyncError):
            gcal.find_or_create_calendar(api)


class TestCalendarIdCache(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix='lazy-gcal-cache-')
        self.cache = os.path.join(self.dir, 'lazy-calendar-id')
        self.api = FakeApi()
        self._patches = [mock.patch.object(gcal, 'credentials', return_value={}),
                         mock.patch.object(gcal, 'access_token', return_value='tok'),
                         mock.patch.object(gcal, 'Api', return_value=self.api)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.dir, ignore_errors=True)

    def lookups(self):
        return sum(1 for c in self.api.calls if c[1] == '/users/me/calendarList')

    def test_second_sync_skips_the_calendar_lookup(self):
        gcal.sync([], None, cache_path=self.cache)
        self.assertEqual(open(self.cache).read().strip(), 'cal1')
        self.assertEqual(self.lookups(), 1)
        gcal.sync([], None, cache_path=self.cache)
        self.assertEqual(self.lookups(), 1)

    def test_a_stale_cached_id_falls_back_to_the_lookup_once(self):
        with open(self.cache, 'w') as f:
            f.write('gone-calendar\n')
        n = gcal.sync([task(1, 'A', '2026-11-03')], None, cache_path=self.cache)
        self.assertEqual(n['created'], 1)
        self.assertEqual(self.lookups(), 1)
        self.assertEqual(open(self.cache).read().strip(), 'cal1')

    def test_no_cache_path_means_a_lookup_every_time(self):
        gcal.sync([], None)
        gcal.sync([], None)
        self.assertEqual(self.lookups(), 2)


class TestSyncEntryPoint(unittest.TestCase):
    def test_missing_credentials_warn_and_skip_without_network(self):
        warnings = []
        with mock.patch.object(gcal, '_keyring', return_value=''), \
             mock.patch.object(gcal, 'access_token', side_effect=AssertionError('network')):
            self.assertIsNone(gcal.sync([], None, 'svc', warn=warnings.append))
        self.assertEqual(len(warnings), 1)
        self.assertIn("client_id/client_secret/refresh_token in keyring service 'svc'", warnings[0])

    def test_unexpected_exception_becomes_a_warning(self):
        warnings = []
        with mock.patch.object(gcal, 'credentials', side_effect=KeyError('boom')):
            self.assertIsNone(gcal.sync([], None, warn=warnings.append))
        self.assertEqual(warnings, ["KeyError: 'boom'"])


class CalendarStore(unittest.TestCase):
    """A Store wired to a FakeApi through the real gcal.sync path."""

    def setUp(self):
        self.repo_path = tempfile.mkdtemp(prefix='lazy-gcal-store-')
        _setup_repo(self.repo_path)
        self.api = FakeApi()
        self._patches = [
            mock.patch.object(gcal, 'credentials', return_value={}),
            mock.patch.object(gcal, 'access_token', return_value='tok'),
            mock.patch.object(gcal, 'Api', return_value=self.api),
        ]
        for p in self._patches:
            p.start()
        self.store = Store(self.repo_path, no_remote=True, calendar='svc')

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def calendar(self):
        """{lazy_id: (start, end, summary)} as the calendar currently holds it."""
        return {int(e['extendedProperties']['private']['lazy_id']):
                (e['start']['date'], e['end']['date'], e['summary'])
                for e in self.api.live().values()}

    def pending(self):
        return {t['id']: (t['due_date'], _next_day(t['due_date']), t['description'])
                for t in self.store.get_tasks('all')}

    def assertMirrored(self):
        self.assertEqual(self.calendar(), self.pending())

    def event(self, lid):
        return event_of(self.api, lid)


class TestStoreToCalendar(CalendarStore):
    """Every store mutation, through the real sync path. Dates are the point."""

    def test_move_rewrites_start_and_end(self):
        tid = self.store.add_task('Call the plumber', date(2026, 11, 3))
        self.assertEqual(self.calendar()[tid][:2], ('2026-11-03', '2026-11-04'))
        self.store.move_task(tid, date(2026, 11, 20))
        self.assertEqual(self.calendar()[tid][:2], ('2026-11-20', '2026-11-21'))
        self.assertEqual([c[0] for c in self.api.mutations()], ['POST', 'PUT'])
        self.assertMirrored()

    def test_move_across_month_year_and_leap_day(self):
        tid = self.store.add_task('Boundary', date(2026, 11, 30))
        for due, end in ((date(2026, 11, 30), '2026-12-01'),
                         (date(2026, 12, 31), '2027-01-01'),
                         (date(2028, 2, 29), '2028-03-01'),
                         (date(2027, 2, 28), '2027-03-01')):
            self.store.move_task(tid, due)
            self.assertEqual(self.calendar()[tid][:2], (due.isoformat(), end), due)
        self.assertMirrored()

    def test_move_into_the_past_keeps_the_event_on_that_day(self):
        tid = self.store.add_task('Late', date.today())
        self.store.move_task(tid, date.today() - timedelta(days=3))
        self.assertEqual(self.calendar()[tid][0], (date.today() - timedelta(days=3)).isoformat())
        self.assertMirrored()

    def test_push_moves_only_todays_and_overdue_events(self):
        today = date.today()
        a = self.store.add_task('Overdue', today - timedelta(days=2))
        b = self.store.add_task('Today', today)
        c = self.store.add_task('Later', today + timedelta(days=3))
        self.api.calls.clear()
        self.assertEqual(self.store.push_tasks(), 2)
        tomorrow = (today + timedelta(days=1)).isoformat()
        self.assertEqual(self.calendar()[a][0], tomorrow)
        self.assertEqual(self.calendar()[b][0], tomorrow)
        self.assertEqual(self.calendar()[c][0], (today + timedelta(days=3)).isoformat())
        self.assertEqual([c[0] for c in self.api.mutations()], ['PUT', 'PUT'])
        self.assertMirrored()

    def test_done_and_delete_remove_events_rename_changes_summary(self):
        a = self.store.add_task('Finish', date(2026, 11, 3))
        b = self.store.add_task('Abandon', date(2026, 11, 4))
        c = self.store.add_task('Misspelt', date(2026, 11, 5))
        self.store.complete_task(a)
        self.assertNotIn(a, self.calendar())
        self.store.delete_task(b)
        self.assertNotIn(b, self.calendar())
        self.store.rename_task(c, 'Spelt right')
        self.assertEqual(self.calendar()[c][2], 'Spelt right')
        self.assertMirrored()

    def test_calendar_heals_after_a_skipped_sync(self):
        a = self.store.add_task('First', date(2026, 11, 3))
        with mock.patch.object(gcal, 'access_token', side_effect=gcal.CalendarSyncError('offline')), \
             mock.patch('sys.stderr'):
            self.store.move_task(a, date(2026, 11, 9))         # mirror skipped
            b = self.store.add_task('Second', date(2026, 11, 4))  # mirror skipped
        self.assertEqual(self.calendar()[a][0], '2026-11-03')   # still stale
        self.assertNotIn(b, self.calendar())
        self.store.rename_task(b, 'Second, renamed')            # next write heals everything
        self.assertMirrored()


class TestCalendarToStore(CalendarStore):
    """Calendar-side edits land in tasks.jsonl, in the same commit as the
    write that noticed them, with the next free id for adopted events."""

    def test_event_move_lands_in_the_file_on_the_next_write(self):
        a = self.store.add_task('Call the plumber', date(2026, 11, 3))
        ev = self.event(a)
        ev['start'], ev['end'] = {'date': '2026-11-10'}, {'date': '2026-11-11'}
        self.store.add_task('Unrelated', date(2026, 11, 4))
        self.assertEqual(self.store.last_inbound, '1 edited')
        self.assertEqual(self.store.get_task(a)['due_date'], '2026-11-10')
        self.assertMirrored()

    def test_event_delete_marks_the_task_done(self):
        a = self.store.add_task('Call the plumber', date(2026, 11, 3))
        self.api('DELETE', '/calendars/cal1/events/' + self.event(a)['id'])
        self.store.add_task('Unrelated', date(2026, 11, 4))
        self.assertEqual(self.store.last_inbound, '1 done')
        self.assertEqual(self.store.get_task(a)['status'], 'done')
        self.assertMirrored()

    def test_hand_made_event_gets_the_next_id_even_past_unparseable_lines(self):
        self.store.add_task('One', date(2026, 11, 3))
        with open(os.path.join(self.repo_path, 'tasks.jsonl'), 'a') as f:
            f.write('{"id": 41, "description": "truncated line\n')   # id 41 is taken
        self.api.add_manual('From the calendar', {'date': '2026-11-15'})
        self.store.add_task('Two', date(2026, 11, 4))
        self.assertEqual(self.store.last_inbound, '1 adopted')
        by_desc = {t['description']: t for t in self.store.get_tasks('all')}
        self.assertEqual(by_desc['Two']['id'], 42, "the explicit add runs before the mirror")
        self.assertEqual((by_desc['From the calendar']['id'], by_desc['From the calendar']['due_date']),
                         (43, '2026-11-15'))
        self.assertMirrored()

    def test_sync_with_a_remote_commits_inbound_changes(self):
        remote = tempfile.mkdtemp(prefix='lazy-gcal-remote-')
        try:
            from tests_common import git as _git
            _git(['init', '-q', '--bare', '-b', 'main'], cwd=remote)
            _git(['remote', 'add', 'origin', remote], cwd=self.repo_path)
            online = Store(self.repo_path, auto_push=True, pull_freshness=0, calendar='svc')
            a = online.add_task('Call the plumber', date(2026, 11, 3))
            self.api.add_manual('Buy stamps', {'date': '2026-11-15'})
            self.api('DELETE', '/calendars/cal1/events/' + self.event(a)['id'])
            self.assertEqual(online.sync(), '1 adopted, 1 done')
            log = _git(['log', '-1', '--format=%s'], cwd=self.repo_path).stdout.strip()
            self.assertEqual(log, 'calendar sync (gcal: 1 adopted, 1 done)')
            self.assertEqual(_git(['rev-list', '--count', '@{u}..HEAD'], cwd=self.repo_path).stdout.strip(), '0')
            self.assertEqual(online.sync(), '', 'nothing new on the second pass')
        finally:
            shutil.rmtree(remote, ignore_errors=True)


class TestWriteCostControls(CalendarStore):
    """The four changes that trim a write without changing what it means."""

    def test_calendar_on_write_false_defers_to_sync(self):
        remote = tempfile.mkdtemp(prefix='lazy-gcal-remote-')
        try:
            from tests_common import git as _git
            _git(['init', '-q', '--bare', '-b', 'main'], cwd=remote)
            _git(['remote', 'add', 'origin', remote], cwd=self.repo_path)
            s = Store(self.repo_path, auto_push=True, pull_freshness=0, calendar='svc',
                      calendar_on_write=False)
            s.add_task('Deferred', date(2026, 11, 3))
            self.assertEqual(self.api.live(), {}, "no Google call on the write")
            self.assertEqual(s.last_inbound, '')
            self.assertEqual(s.sync(), '')
            self.assertEqual(len(self.api.live()), 1, "`lazy sync` still reconciles")
        finally:
            shutil.rmtree(remote, ignore_errors=True)

    def test_on_write_flag_comes_from_user_config(self):
        cfg = {'repo_path': self.repo_path, 'calendar_sync': True, 'calendar_sync_on_write': False}
        with mock.patch.object(store_mod, '_read_user_config', return_value=cfg):
            s = store_mod.open_store()
        self.assertEqual((s.calendar, s.calendar_on_write), ('google-workspace-mcp', False))
        with mock.patch.object(store_mod, '_read_user_config', return_value={'repo_path': self.repo_path}):
            self.assertTrue(store_mod.open_store().calendar_on_write)

    def test_a_write_inside_the_freshness_window_does_not_pull(self):
        remote = tempfile.mkdtemp(prefix='lazy-gcal-remote-')
        try:
            from tests_common import git as _git
            _git(['init', '-q', '--bare', '-b', 'main'], cwd=remote)
            _git(['remote', 'add', 'origin', remote], cwd=self.repo_path)
            s = Store(self.repo_path, auto_push=True, pull_freshness=30, calendar=None)
            s.add_task('First', date(2026, 11, 3))          # pushes; sentinel touched
            with mock.patch.object(store_mod.git_ops, 'pull_ff', wraps=store_mod.git_ops.pull_ff) as pull:
                s.add_task('Second', date(2026, 11, 4))
                self.assertEqual(pull.call_count, 0, "fresh sentinel: no pull before the write")
                os.utime(s._sentinel, (0, 0))
                s.add_task('Third', date(2026, 11, 5))
                self.assertEqual(pull.call_count, 1, "stale sentinel: pull before the write")
        finally:
            shutil.rmtree(remote, ignore_errors=True)

    def test_a_warm_read_spawns_no_git(self):
        s = Store(self.repo_path, no_remote=False, pull_freshness=30)
        s._touch_sentinel()
        with mock.patch.object(store_mod.git_ops, '_run', wraps=store_mod.git_ops._run) as run:
            s.get_tasks('today')
            self.assertEqual(run.call_count, 0)
            os.makedirs(os.path.join(self.repo_path, '.git', 'rebase-merge'))
            s.get_tasks('today')
            self.assertGreater(run.call_count, 0, "an interrupted rebase is still noticed at once")

    def test_nothing_committed_means_nothing_pushed(self):
        remote = tempfile.mkdtemp(prefix='lazy-gcal-remote-')
        try:
            from tests_common import git as _git
            _git(['init', '-q', '--bare', '-b', 'main'], cwd=remote)
            _git(['remote', 'add', 'origin', remote], cwd=self.repo_path)
            s = Store(self.repo_path, auto_push=True, pull_freshness=0, calendar='svc')
            s.add_task('One', date(2026, 11, 3))
            with mock.patch.object(store_mod.git_ops, 'push', wraps=store_mod.git_ops.push) as push:
                self.assertEqual(s.sync(), '')
                self.assertEqual(push.call_count, 1, "sync's own push, not a second one for the no-op cycle")
                self.api.add_manual('From the calendar', {'date': '2026-11-15'})
                self.assertEqual(s.sync(), '1 adopted')
                self.assertEqual(push.call_count, 3, "a real inbound commit is pushed")
        finally:
            shutil.rmtree(remote, ignore_errors=True)


class TestImportsStayOffTheReadPath(unittest.TestCase):
    def test_bare_lazy_imports_neither_urllib_nor_argparse(self):
        import subprocess
        repo = tempfile.mkdtemp(prefix='lazy-import-test-')
        try:
            _setup_repo(repo)
            r = subprocess.run([sys.executable, '-X', 'importtime', os.path.join(os.path.dirname(__file__), 'lazy')],
                               capture_output=True, text=True,
                               env={**os.environ, 'LAZY_HOME': repo, 'LAZY_NO_REMOTE': '1'})
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
            imported = {line.split('|')[-1].strip() for line in r.stderr.splitlines() if '|' in line}
            for mod in ('urllib.request', 'ssl', 'argparse', 'tempfile', 'gcal'):
                self.assertNotIn(mod, imported, f"{mod} imported on a bare read")
        finally:
            shutil.rmtree(repo, ignore_errors=True)


class TestSyncIsHonest(CalendarStore):
    def test_sync_returns_none_when_a_leg_fails(self):
        with mock.patch('sys.stderr'):
            self.assertIsNone(self.store.sync(), "no remote is not a successful sync")
        remote = tempfile.mkdtemp(prefix='lazy-gcal-remote-')
        try:
            from tests_common import git as _git
            _git(['init', '-q', '--bare', '-b', 'main'], cwd=remote)
            _git(['remote', 'add', 'origin', remote], cwd=self.repo_path)
            online = Store(self.repo_path, auto_push=True, pull_freshness=0, calendar='svc')
            online.add_task('One', date(2026, 11, 3))
            self.assertEqual(online.sync(), '')
            with mock.patch.object(gcal, 'access_token', side_effect=gcal.CalendarSyncError('offline')), \
                 mock.patch('sys.stderr'):
                self.assertIsNone(online.sync(), "a skipped calendar reconcile is not success")
            shutil.rmtree(remote)
            with mock.patch('sys.stderr'):
                self.assertIsNone(online.sync(), "a failed pull is not success")
        finally:
            shutil.rmtree(remote, ignore_errors=True)

    def test_cli_sync_exits_nonzero_on_failure(self):
        import subprocess
        r = subprocess.run([os.path.join(os.path.dirname(__file__), 'lazy'), 'sync'],
                           capture_output=True, text=True,
                           env={**os.environ, 'LAZY_HOME': self.repo_path, 'LAZY_NO_REMOTE': '1'})
        self.assertEqual(r.returncode, 1)
        self.assertIn('no remote configured', r.stderr)
        self.assertIn('Sync failed', r.stderr)


class TestTwoMachines(unittest.TestCase):
    """Two synced machines sharing one calendar. The second machine's push is
    delayed; the first machine's timer must not mistake the orphaned event
    for stale, nor its own clean-up for a user deletion."""

    def setUp(self):
        from tests_common import git as _git, set_identity as _set_identity
        self.tmp = tempfile.mkdtemp(prefix='lazy-gcal-race-')
        self.remote, self.a, self.b = (os.path.join(self.tmp, d) for d in ('remote.git', 'A', 'B'))
        os.makedirs(self.remote)
        _git(['init', '-q', '--bare', '-b', 'main'], cwd=self.remote)
        for path in (self.a, self.b):
            _git(['clone', '-q', self.remote, path], cwd=self.tmp)
            _set_identity(path)
            _git(['config', 'push.default', 'current'], cwd=path)
        self.api = FakeApi()
        self._patches = [mock.patch.object(gcal, 'credentials', return_value={}),
                         mock.patch.object(gcal, 'access_token', return_value='tok'),
                         mock.patch.object(gcal, 'Api', return_value=self.api)]
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_a_task_added_while_its_push_is_delayed_survives_the_other_machines_timer(self):
        A = Store(self.a, auto_push=True, pull_freshness=0, calendar='svc')
        A.add_task('seed', date(2026, 11, 1))
        B_offline = Store(self.b, auto_push=False, pull_freshness=0, calendar='svc')
        n = B_offline.add_task('Added on B while its push was failing', date(2026, 11, 5))
        self.assertEqual(A.sync(), '')                       # A's timer: B's event looks stale, goes
        self.assertEqual(len(self.api.live()), 1)
        Store(self.b, auto_push=True, pull_freshness=0, calendar='svc').get_tasks('all')  # B flushes
        self.assertEqual(A.sync(), '')                       # A's next tick: recreated, never "done"
        self.assertEqual(A.get_task(n)['status'], 'pending')
        self.assertEqual(len(self.api.live()), 2)

    def test_a_task_done_on_one_machine_is_not_resurrected_by_the_other(self):
        A = Store(self.a, auto_push=True, pull_freshness=0, calendar='svc')
        n = A.add_task('Finish it', date(2026, 11, 1))
        B = Store(self.b, auto_push=True, pull_freshness=0, calendar='svc')
        B.get_tasks('all')
        A.complete_task(n)                                   # A deletes the event, marked as lazy's
        self.assertEqual(B.sync(), '')                       # B pulls the done, sees the tombstone
        self.assertEqual(B.get_task(n)['status'], 'done')
        self.assertEqual(self.api.live(), {})


class TestStoreHook(unittest.TestCase):
    def setUp(self):
        self.repo_path = tempfile.mkdtemp(prefix='lazy-gcal-test-')
        _setup_repo(self.repo_path)

    def tearDown(self):
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def test_mirror_failure_does_not_undo_the_write(self):
        with mock.patch.object(gcal, 'access_token', side_effect=gcal.CalendarSyncError('offline')), \
             mock.patch.object(gcal, 'credentials', return_value={}), \
             mock.patch('sys.stderr') as err:
            s = Store(self.repo_path, no_remote=True, calendar='svc')
            s.add_task('Survives', '2026-11-03')
        self.assertEqual([t['description'] for t in read_tasks(self.repo_path)], ['Survives'])
        self.assertIn('calendar sync skipped: offline', ''.join(c.args[0] for c in err.write.call_args_list))

    def test_mirror_is_off_by_default(self):
        with mock.patch.object(gcal, 'sync') as sync:
            Store(self.repo_path, no_remote=True).add_task('Quiet', '2026-11-03')
        sync.assert_not_called()

    def test_user_config_switch(self):
        self.assertIsNone(store_mod.calendar_service({}))
        self.assertIsNone(store_mod.calendar_service({'calendar_sync': False}))
        self.assertEqual(store_mod.calendar_service({'calendar_sync': True}), 'google-workspace-mcp')
        self.assertEqual(store_mod.calendar_service(
            {'calendar_sync': True, 'calendar_keyring_service': 'mine'}), 'mine')


if __name__ == '__main__':
    unittest.main()
