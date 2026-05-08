import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _setup_repo(path):
    """Create an empty git repo with a configured identity."""
    subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=path, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=path, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=path, check=True)


class IsolatedStore(unittest.TestCase):
    """Base: routes store calls to a tempdir-backed git repo, no remote."""

    def setUp(self):
        self.repo_path = tempfile.mkdtemp(prefix='lazy-test-')
        _setup_repo(self.repo_path)
        os.environ['LAZY_HOME'] = self.repo_path
        os.environ['LAZY_NO_REMOTE'] = '1'

    def tearDown(self):
        os.environ.pop('LAZY_HOME', None)
        os.environ.pop('LAZY_NO_REMOTE', None)
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def read_jsonl(self):
        path = os.path.join(self.repo_path, 'tasks.jsonl')
        if not os.path.exists(path):
            return []
        out = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    obj = json.loads(line)
                    if 'id' in obj:
                        out.append(obj)
        return out


class TestParseDate(unittest.TestCase):
    def test_keywords(self):
        from utils import parse_date
        today = date.today()
        self.assertEqual(parse_date("today"), today)
        self.assertEqual(parse_date("tod"), today)
        self.assertEqual(parse_date("tmw"), today + timedelta(days=1))
        self.assertEqual(parse_date("tom"), today + timedelta(days=1))
        self.assertEqual(parse_date("tomorrow"), today + timedelta(days=1))
        self.assertEqual(parse_date("yesterday"), today - timedelta(days=1))

    def test_offsets(self):
        from utils import parse_date
        today = date.today()
        self.assertEqual(parse_date("+1"), today + timedelta(days=1))
        self.assertEqual(parse_date("+7"), today + timedelta(days=7))
        self.assertEqual(parse_date("3"), today + timedelta(days=3))
        self.assertEqual(parse_date("2w"), today + timedelta(weeks=2))
        self.assertEqual(parse_date("+1w"), today + timedelta(weeks=1))

    def test_fuzzy_phrases(self):
        from utils import parse_date
        today = date.today()
        self.assertEqual(parse_date("in 3 days"), today + timedelta(days=3))
        self.assertEqual(parse_date("in 2 weeks"), today + timedelta(weeks=2))
        self.assertEqual(parse_date("5 days"), today + timedelta(days=5))

    def test_special_phrases(self):
        from utils import parse_date
        today = date.today()
        self.assertEqual(parse_date("soon"), today + timedelta(days=3))
        self.assertEqual(parse_date("later"), today + timedelta(days=7))
        self.assertEqual(parse_date("someday"), today + timedelta(days=30))
        self.assertEqual(parse_date("eventually"), today + timedelta(days=30))

    def test_milestones(self):
        from utils import parse_date
        d = parse_date("eom")
        self.assertEqual(d.year, date.today().year)
        self.assertEqual(d.month, date.today().month)
        self.assertEqual(parse_date("eoy"), date(date.today().year, 12, 31))

    def test_weekday_returns_correct_day(self):
        from utils import parse_date
        today = date.today()
        d = parse_date("fri")
        self.assertEqual(d.weekday(), 4)
        self.assertGreater(d, today)
        self.assertLessEqual(d, today + timedelta(days=7))

    def test_lazy_next_skips_current_week(self):
        """README's marquee feature: 'next fri' picks the Friday AFTER this week's."""
        from utils import parse_date
        plain = parse_date("fri")
        nxt = parse_date("next fri")
        self.assertEqual(plain.weekday(), 4)
        self.assertEqual(nxt.weekday(), 4)
        self.assertGreaterEqual((nxt - plain).days, 7)

    def test_next_weekday_always_skips_for_every_starting_day(self):
        """'next <day>' must be exactly 7 days after '<day>' regardless of
        today's weekday. Regression: previously returned the same date as
        '<day>' when today happened to be Friday or Saturday."""
        from utils import parse_date
        base = date(2026, 1, 5)  # known Monday
        days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        for offset in range(7):
            today = base + timedelta(days=offset)
            for day in days:
                plain = parse_date(day, today=today)
                nxt = parse_date(f"next {day}", today=today)
                gap = (nxt - plain).days
                self.assertEqual(
                    gap, 7,
                    f"on {today.strftime('%A')}, '{day}'={plain}, "
                    f"'next {day}'={nxt}, gap={gap}, expected 7"
                )

    def test_explicit_dates(self):
        from utils import parse_date
        self.assertEqual(parse_date("2025-12-17"), date(2025, 12, 17))
        self.assertEqual(parse_date("12-17").month, 12)
        self.assertEqual(parse_date("12/17").month, 12)

    def test_unparseable_raises(self):
        from utils import parse_date
        with self.assertRaises(ValueError):
            parse_date("not a real date string")


class TestVibeEcho(unittest.TestCase):
    def test_returns_nonempty_string(self):
        from utils import get_vibe_echo
        echo = get_vibe_echo("Buy Milk", date.today())
        self.assertIsInstance(echo, str)
        self.assertGreater(len(echo), 0)


class TestStore(IsolatedStore):
    def test_add_and_fetch(self):
        from store import open_store
        store = open_store()
        tid = store.add_task("hello", date.today())
        row = store.get_task(tid)
        self.assertEqual(row['description'], "hello")
        self.assertEqual(row['status'], 'pending')

    def test_complete(self):
        from store import open_store
        store = open_store()
        tid = store.add_task("done me", date.today())
        store.complete_task(tid)
        self.assertEqual(store.get_task(tid)['status'], 'done')

    def test_get_tasks_today_excludes_future(self):
        from store import open_store
        store = open_store()
        store.add_task("overdue", date.today() - timedelta(days=1))
        store.add_task("today", date.today())
        store.add_task("future", date.today() + timedelta(days=5))
        today_rows = store.get_tasks('today')
        descs = [r['description'] for r in today_rows]
        self.assertIn("overdue", descs)
        self.assertIn("today", descs)
        self.assertNotIn("future", descs)
        all_rows = store.get_tasks('all')
        self.assertEqual(len(all_rows), 3)

    def test_push_moves_today_and_overdue_only(self):
        from store import open_store
        store = open_store()
        today = date.today()
        store.add_task("Old", today - timedelta(days=1))
        store.add_task("Today", today)
        store.add_task("Future", today + timedelta(days=1))
        count = store.push_tasks()
        self.assertEqual(count, 2)
        for t in store.get_tasks('all'):
            self.assertGreaterEqual(date.fromisoformat(t['due_date']), today + timedelta(days=1))

    def test_rename_unknown_id_raises(self):
        from store import open_store
        store = open_store()
        with self.assertRaises(ValueError):
            store.rename_task(99999, "ghost")

    def test_delete(self):
        from store import open_store
        store = open_store()
        tid = store.add_task("trash", date.today())
        store.delete_task(tid)
        self.assertIsNone(store.get_task(tid))

    def test_metadata_lines_are_skipped(self):
        """A line without an 'id' field should be silently ignored on read."""
        from store import open_store
        path = os.path.join(self.repo_path, 'tasks.jsonl')
        with open(path, 'w') as f:
            f.write('{"_init": true}\n')
            f.write('{"id":1,"description":"real","due_date":"2030-01-01","status":"pending"}\n')
        store = open_store()
        tasks = store.get_tasks('all')
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]['description'], 'real')

    def test_writes_are_committed(self):
        """After a write, the repo should have a clean working tree (commit happened)."""
        from store import open_store
        store = open_store()
        store.add_task("commit me", date.today())
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=self.repo_path, capture_output=True, text=True
        )
        self.assertEqual(result.stdout.strip(), '',
                         f"expected clean tree, got: {result.stdout!r}")
        log = subprocess.run(
            ['git', 'log', '--oneline'],
            cwd=self.repo_path, capture_output=True, text=True
        )
        self.assertIn("add: commit me", log.stdout)


if __name__ == "__main__":
    unittest.main()
