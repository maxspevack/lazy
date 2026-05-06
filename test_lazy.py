"""End-to-end CLI tests via subprocess. Slow but exercises argparse + dispatch."""

import os
import sqlite3
import subprocess
import tempfile
import unittest
from datetime import date, timedelta


class TestLazyCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lazy_bin = os.path.join(os.path.dirname(__file__), 'lazy')

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(prefix='lazy-cli-test-', suffix='.db')
        os.close(fd)
        self.env = {**os.environ, 'LAZY_DB_PATH': self.db_path}

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)

    def run_lazy(self, *args):
        return subprocess.run(
            [self.lazy_bin] + list(args),
            capture_output=True, text=True, env=self.env
        )

    def latest_id(self, description):
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT id FROM tasks WHERE description = ? ORDER BY id DESC LIMIT 1",
                (description,)
            ).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def test_add_then_list(self):
        self.run_lazy("a", "Test alpha", "today")
        self.assertIn("Test alpha", self.run_lazy("l").stdout)

    def test_implicit_add_no_command_word(self):
        """README's headline feature: lazy <words> [date] should infer add."""
        self.run_lazy("Buy eggs", "tomorrow")
        out = self.run_lazy("l").stdout
        self.assertIn("Buy eggs", out)

    def test_implicit_add_strips_trailing_preposition(self):
        """'fold laundry on tuesday' should store 'fold laundry', not 'fold laundry on'."""
        self.run_lazy("fold laundry", "on", "tuesday")
        conn = sqlite3.connect(self.db_path)
        try:
            descs = [r[0] for r in conn.execute("SELECT description FROM tasks").fetchall()]
        finally:
            conn.close()
        self.assertIn("fold laundry", descs)
        for d in descs:
            self.assertFalse(d.endswith(" on"), f"preposition not stripped: {d!r}")

    def test_done_marks_complete(self):
        self.run_lazy("a", "kill it", "today")
        tid = self.latest_id("kill it")
        self.run_lazy("d", str(tid))
        conn = sqlite3.connect(self.db_path)
        try:
            status = conn.execute("SELECT status FROM tasks WHERE id=?", (tid,)).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status, 'done')

    def test_rename(self):
        self.run_lazy("a", "Original", "today")
        tid = self.latest_id("Original")
        self.run_lazy("rn", str(tid), "Updated")
        out = self.run_lazy("l").stdout
        self.assertIn("Updated", out)
        self.assertNotIn("Original", out)

    def test_view(self):
        self.run_lazy("a", "View me", "today")
        tid = self.latest_id("View me")
        out = self.run_lazy("v", str(tid)).stdout
        self.assertIn("View me", out)
        self.assertIn(str(tid), out)

    def test_move(self):
        self.run_lazy("a", "Movable", "today")
        tid = self.latest_id("Movable")
        self.run_lazy("m", str(tid), "+2")
        target = (date.today() + timedelta(days=2)).isoformat()
        self.assertIn(target, self.run_lazy("l").stdout)

    def test_bump_overdue_goes_to_tomorrow(self):
        """Bumping an overdue task should land tomorrow, not yesterday+1."""
        conn = sqlite3.connect(self.db_path)
        try:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            conn.execute("CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, description TEXT NOT NULL, due_date DATE NOT NULL, status TEXT DEFAULT 'pending', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("INSERT INTO tasks (description, due_date) VALUES (?, ?)", ("late", yesterday))
            conn.commit()
            tid = conn.execute("SELECT id FROM tasks WHERE description='late'").fetchone()[0]
        finally:
            conn.close()
        self.run_lazy("b", str(tid))
        conn = sqlite3.connect(self.db_path)
        try:
            new_date = conn.execute("SELECT due_date FROM tasks WHERE id=?", (tid,)).fetchone()[0]
        finally:
            conn.close()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertEqual(new_date, tomorrow)

    def test_help_alias(self):
        out = self.run_lazy("help").stdout
        self.assertIn("usage:", out)
        self.assertIn("Commands:", out)

    def test_help_does_not_create_task(self):
        """RELEASE_NOTES claims this was fixed in v2026.04.27."""
        self.run_lazy("a", "seed", "today")
        self.run_lazy("help")
        conn = sqlite3.connect(self.db_path)
        try:
            descs = [r[0] for r in conn.execute("SELECT description FROM tasks").fetchall()]
        finally:
            conn.close()
        self.assertNotIn("help", descs)
        self.assertEqual(len(descs), 1)


if __name__ == "__main__":
    unittest.main()
