"""Calendar mirror: reconcile logic against a fake API, and the store hook.
No network. The live path is exercised by hand against a throwaway calendar."""

import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gcal
import store as store_mod
from store import Store
from tests_common import setup_repo as _setup_repo, read_tasks


def task(id_, desc, due, status='pending'):
    return {'id': id_, 'description': desc, 'due_date': due, 'status': status}


class FakeApi:
    """Just enough of the Calendar v3 surface for reconcile()."""

    def __init__(self, calendars=None, events=()):
        self.calendars = calendars if calendars is not None else [{'id': 'cal1', 'summary': 'Lazy'}]
        self.events = {e['id']: e for e in events}
        self.calls = []
        self._n = 0

    def __call__(self, method, path, body=None, **params):
        self.calls.append((method, path))
        if path == '/users/me/calendarList':
            return {'items': self.calendars}
        if path == '/calendars' and method == 'POST':
            self.calendars.append({'id': 'newcal', 'summary': body['summary']})
            return {'id': 'newcal'}
        if path.endswith('/events') and method == 'GET':
            return {'items': list(self.events.values())}
        if path.endswith('/events') and method == 'POST':
            self._n += 1
            ev = dict(body, id=f'ev{self._n}')
            self.events[ev['id']] = ev
            return ev
        event_id = path.rsplit('/', 1)[1]
        if method == 'PUT':
            self.events[event_id] = dict(body, id=event_id)
            return self.events[event_id]
        if method == 'DELETE':
            if event_id not in self.events:
                raise gcal.CalendarSyncError('gone', 410)
            del self.events[event_id]
            return None
        raise AssertionError(f"unexpected {method} {path}")

    def mutations(self):
        return [c for c in self.calls if c[0] != 'GET']


class TestReconcile(unittest.TestCase):
    def test_pending_tasks_become_tagged_all_day_events(self):
        api = FakeApi()
        counts = gcal.reconcile(api, 'cal1', [
            task(1, 'Call Ray', '2026-11-03'),
            task(2, 'Old thing', '2026-10-01', status='done'),
        ])
        self.assertEqual(counts, (1, 0, 0))
        (ev,) = api.events.values()
        self.assertEqual(ev['summary'], 'Call Ray')
        self.assertEqual(ev['start'], {'date': '2026-11-03'})
        self.assertEqual(ev['end'], {'date': '2026-11-04'})
        self.assertEqual(ev['extendedProperties']['private']['lazy_id'], '1')
        self.assertEqual(ev['transparency'], 'transparent')

    def test_second_pass_is_read_only(self):
        api = FakeApi()
        tasks = [task(1, 'Call Ray', '2026-11-03'), task(2, 'Fix faucet', '2027-01-01')]
        gcal.reconcile(api, 'cal1', tasks)
        api.calls.clear()
        self.assertEqual(gcal.reconcile(api, 'cal1', tasks), (0, 0, 0))
        self.assertEqual(api.mutations(), [])

    def test_rename_and_move_update_in_place(self):
        api = FakeApi()
        gcal.reconcile(api, 'cal1', [task(1, 'Call Ray', '2026-11-03')])
        api.calls.clear()
        counts = gcal.reconcile(api, 'cal1', [task(1, 'Call Ray (cell)', '2026-11-05')])
        self.assertEqual(counts, (0, 1, 0))
        self.assertEqual([c[0] for c in api.mutations()], ['PUT'])
        (ev,) = api.events.values()
        self.assertEqual((ev['summary'], ev['start']['date'], ev['end']['date']),
                         ('Call Ray (cell)', '2026-11-05', '2026-11-06'))

    def test_done_and_removed_tasks_lose_their_events(self):
        api = FakeApi()
        gcal.reconcile(api, 'cal1', [task(1, 'A', '2026-11-03'), task(2, 'B', '2026-11-04')])
        counts = gcal.reconcile(api, 'cal1', [task(1, 'A', '2026-11-03', status='done')])
        self.assertEqual(counts, (0, 0, 2))
        self.assertEqual(api.events, {})

    def test_untagged_events_are_never_touched(self):
        manual = {'id': 'm1', 'summary': 'Dentist', 'start': {'date': '2026-11-03'},
                  'end': {'date': '2026-11-04'}}
        api = FakeApi(events=[manual])
        self.assertEqual(gcal.reconcile(api, 'cal1', []), (0, 0, 0))
        self.assertEqual(api.events, {'m1': manual})

    def test_duplicate_tagged_events_collapse_to_one(self):
        t = task(7, 'Twice', '2026-11-03')
        dup = lambda i: dict(gcal._event_for(t), id=f'd{i}')
        api = FakeApi(events=[dup(1), dup(2)])
        self.assertEqual(gcal.reconcile(api, 'cal1', [t]), (0, 0, 1))
        self.assertEqual(list(api.events), ['d1'])

    def test_already_deleted_event_counts_as_deleted(self):
        t = task(3, 'Ghost', '2026-11-03')
        api = FakeApi(events=[dict(gcal._event_for(t), id='g1')])
        real_call = api.__call__
        def racing(method, path, body=None, **params):
            if method == 'GET' and path.endswith('/events'):
                items = list(api.events.values())
                api.events.clear()           # someone else deleted it mid-run
                return {'items': items}
            return real_call(method, path, body, **params)
        self.assertEqual(gcal.reconcile(racing, 'cal1', []), (0, 0, 1))


class TestCalendarLookup(unittest.TestCase):
    def test_existing_calendar_is_reused(self):
        api = FakeApi()
        self.assertEqual(gcal.find_or_create_calendar(api), 'cal1')
        self.assertEqual(api.mutations(), [])

    def test_missing_calendar_is_created(self):
        api = FakeApi(calendars=[{'id': 'p', 'summary': 'max@example.com'}])
        self.assertEqual(gcal.find_or_create_calendar(api), 'newcal')
        self.assertEqual(api.mutations(), [('POST', '/calendars')])

    def test_two_calendars_with_the_name_refuse(self):
        api = FakeApi(calendars=[{'id': 'a', 'summary': 'Lazy'}, {'id': 'b', 'summary': 'Lazy'}])
        with self.assertRaises(gcal.CalendarSyncError):
            gcal.find_or_create_calendar(api)


class TestSyncEntryPoint(unittest.TestCase):
    def test_missing_credentials_warn_and_skip_without_network(self):
        warnings = []
        with mock.patch.object(gcal, '_keyring', return_value=''), \
             mock.patch.object(gcal, 'access_token', side_effect=AssertionError('network')):
            self.assertIsNone(gcal.sync([], 'svc', warn=warnings.append))
        self.assertEqual(len(warnings), 1)
        self.assertIn("client_id/client_secret/refresh_token in keyring service 'svc'", warnings[0])

    def test_unexpected_exception_becomes_a_warning(self):
        warnings = []
        with mock.patch.object(gcal, 'credentials', side_effect=KeyError('boom')):
            self.assertIsNone(gcal.sync([], warn=warnings.append))
        self.assertEqual(warnings, ["KeyError: 'boom'"])


class TestStoreHook(unittest.TestCase):
    def setUp(self):
        self.repo_path = tempfile.mkdtemp(prefix='lazy-gcal-test-')
        _setup_repo(self.repo_path)

    def tearDown(self):
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def test_every_write_mirrors_the_full_task_list(self):
        seen = []
        with mock.patch.object(gcal, 'sync', side_effect=lambda tasks, svc: seen.append((list(tasks), svc))):
            s = Store(self.repo_path, no_remote=True, calendar='svc')
            new_id = s.add_task('Call Ray', '2026-11-03')
            s.complete_task(new_id)
        self.assertEqual([svc for _, svc in seen], ['svc', 'svc'])
        self.assertEqual(seen[0][0][0]['status'], 'pending')
        self.assertEqual(seen[1][0][0]['status'], 'done')

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
