import unittest
from datetime import date, timedelta
import sys
import os

# Ensure we can import from the current directory
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils import parse_date, get_vibe_echo
from db import init_db, add_task, get_tasks, push_tasks, get_connection

class TestLogic(unittest.TestCase):
    def test_parse_date_keywords(self):
        today = date.today()
        self.assertEqual(parse_date("today"), today)
        self.assertEqual(parse_date("tmw"), today + timedelta(days=1))
        self.assertEqual(parse_date("tomorrow"), today + timedelta(days=1))
        self.assertEqual(parse_date("yesterday"), today - timedelta(days=1))

    def test_parse_date_offsets(self):
        today = date.today()
        self.assertEqual(parse_date("+1"), today + timedelta(days=1))
        self.assertEqual(parse_date("+7"), today + timedelta(days=7))
        self.assertEqual(parse_date("3"), today + timedelta(days=3))
        self.assertEqual(parse_date("2w"), today + timedelta(weeks=2))
        self.assertEqual(parse_date("+1w"), today + timedelta(weeks=1))

    def test_parse_date_fuzzy(self):
        today = date.today()
        self.assertEqual(parse_date("in 3 days"), today + timedelta(days=3))
        self.assertEqual(parse_date("in 2 weeks"), today + timedelta(weeks=2))
        self.assertEqual(parse_date("5 days"), today + timedelta(days=5))

    def test_parse_date_special(self):
        today = date.today()
        self.assertEqual(parse_date("soon"), today + timedelta(days=3))
        self.assertEqual(parse_date("later"), today + timedelta(days=7))
        self.assertEqual(parse_date("someday"), today + timedelta(days=30))

    def test_parse_date_weekdays_standard(self):
        # This test is tricky because it depends on 'today'
        # Let's just verify it returns a date in the future (or today+7)
        today = date.today()
        d = parse_date("fri")
        self.assertGreater(d, today)
        self.assertEqual(d.weekday(), 4) # Friday is 4
        self.assertLessEqual(d, today + timedelta(days=7))

    def test_parse_date_lazy_next(self):
        # Max's Logic check
        today = date.today()
        # If we are on a Sunday (6), "next mon" should be +8 days
        # We can't easily mock date.today() without freezegun, 
        # but we can test the logic if we know what today is.
        
        # Test "next" keyword existence
        d = parse_date("next fri")
        self.assertGreater(d, today + timedelta(days=0))
        self.assertEqual(d.weekday(), 4)

    def test_vibe_echo(self):
        desc = "Buy Milk"
        d = date.today()
        echo = get_vibe_echo(desc, d)
        self.assertIsInstance(echo, str)
        # Even if random, it should likely contain the description or date if using defaults
        # But since config.json has many persona messages, we just check it returns something.
        self.assertTrue(len(echo) > 0)

    def test_db_push(self):
        init_db()
        conn = get_connection()
        # Clear existing tasks for this test
        conn.execute("DELETE FROM tasks")
        conn.commit()
        
        today = date.today()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)
        
        add_task("Old Task", yesterday, conn=conn)
        add_task("Today Task", today, conn=conn)
        add_task("Future Task", tomorrow, conn=conn)
        
        count = push_tasks(conn=conn)
        self.assertEqual(count, 2) # Yesterday and Today should be pushed
        
        tasks = get_tasks('all', conn=conn)
        for t in tasks:
            t_date = date.fromisoformat(t['due_date'])
            self.assertGreaterEqual(t_date, tomorrow)
        
        conn.close()

if __name__ == "__main__":
    unittest.main()
