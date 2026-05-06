import os
import sys
import tempfile
import unittest
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class IsolatedDB(unittest.TestCase):
    """Base: routes db calls to a tempfile, importing modules fresh after env is set."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix='lazy-test-', suffix='.db')
        os.close(fd)
        os.environ['LAZY_DB_PATH'] = self.db_path

    def tearDown(self):
        os.environ.pop('LAZY_DB_PATH', None)
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)


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
        today = date.today()
        plain = parse_date("fri")
        nxt = parse_date("next fri")
        self.assertEqual(plain.weekday(), 4)
        self.assertEqual(nxt.weekday(), 4)
        self.assertGreaterEqual((nxt - plain).days, 7)

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


class TestDB(IsolatedDB):
    def test_add_and_fetch(self):
        from db import get_connection, add_task, get_task
        conn = get_connection()
        try:
            tid = add_task("hello", date.today(), conn)
            row = get_task(tid, conn)
            self.assertEqual(row['description'], "hello")
            self.assertEqual(row['status'], 'pending')
        finally:
            conn.close()

    def test_complete(self):
        from db import get_connection, add_task, complete_task, get_task
        conn = get_connection()
        try:
            tid = add_task("done me", date.today(), conn)
            complete_task(tid, conn)
            self.assertEqual(get_task(tid, conn)['status'], 'done')
        finally:
            conn.close()

    def test_get_tasks_today_excludes_future(self):
        from db import get_connection, add_task, get_tasks
        conn = get_connection()
        try:
            add_task("overdue", date.today() - timedelta(days=1), conn)
            add_task("today", date.today(), conn)
            add_task("future", date.today() + timedelta(days=5), conn)
            today_rows = get_tasks('today', conn)
            descs = [r['description'] for r in today_rows]
            self.assertIn("overdue", descs)
            self.assertIn("today", descs)
            self.assertNotIn("future", descs)
            all_rows = get_tasks('all', conn)
            self.assertEqual(len(all_rows), 3)
        finally:
            conn.close()

    def test_push_moves_today_and_overdue_only(self):
        from db import get_connection, add_task, get_tasks, push_tasks
        conn = get_connection()
        try:
            today = date.today()
            add_task("Old", today - timedelta(days=1), conn)
            add_task("Today", today, conn)
            add_task("Future", today + timedelta(days=1), conn)
            count = push_tasks(conn)
            self.assertEqual(count, 2)
            for t in get_tasks('all', conn):
                self.assertGreaterEqual(date.fromisoformat(t['due_date']), today + timedelta(days=1))
        finally:
            conn.close()

    def test_rename_unknown_id_raises(self):
        from db import get_connection, rename_task
        conn = get_connection()
        try:
            with self.assertRaises(ValueError):
                rename_task(99999, "ghost", conn)
        finally:
            conn.close()

    def test_delete(self):
        from db import get_connection, add_task, delete_task, get_task
        conn = get_connection()
        try:
            tid = add_task("trash", date.today(), conn)
            delete_task(tid, conn)
            self.assertIsNone(get_task(tid, conn))
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
