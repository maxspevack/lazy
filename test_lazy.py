import unittest
import subprocess
import os
import sqlite3
from datetime import date, timedelta

class TestLazy(unittest.TestCase):
    def setUp(self):
        self.db_path = os.path.join(os.path.dirname(__file__), 'lazy.db')
        self.lazy_bin = os.path.join(os.path.dirname(__file__), 'lazy')
        
    def run_lazy(self, *args):
        result = subprocess.run([self.lazy_bin] + list(args), capture_output=True, text=True)
        return result

    def test_add_and_list(self):
        desc = f"Test Task {os.getpid()}"
        self.run_lazy("a", desc, "today")
        res = self.run_lazy("l")
        self.assertIn(desc, res.stdout)

    def test_rename(self):
        desc = "Original Description"
        self.run_lazy("a", desc)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM tasks WHERE description = ? ORDER BY id DESC LIMIT 1", (desc,))
        task_id = c.fetchone()[0]
        conn.close()
        
        new_desc = "Updated Description"
        self.run_lazy("rn", str(task_id), new_desc)
        
        res = self.run_lazy("l")
        self.assertIn(new_desc, res.stdout)
        self.assertNotIn(desc, res.stdout)

    def test_view(self):
        desc = "View Test Task"
        self.run_lazy("a", desc)
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM tasks WHERE description = ? ORDER BY id DESC LIMIT 1", (desc,))
        task_id = c.fetchone()[0]
        conn.close()
        
        res = self.run_lazy("v", str(task_id))
        self.assertIn(desc, res.stdout)
        self.assertIn("ID:", res.stdout)
        self.assertIn(str(task_id), res.stdout)

    def test_move(self):
        desc = "Move Test Task"
        self.run_lazy("a", desc, "today")
        
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id FROM tasks WHERE description = ? ORDER BY id DESC LIMIT 1", (desc,))
        task_id = c.fetchone()[0]
        conn.close()
        
        new_date = (date.today() + timedelta(days=2)).isoformat()
        self.run_lazy("m", str(task_id), "+2")
        
        res = self.run_lazy("l")
        self.assertIn(new_date, res.stdout)

    def test_help_alias(self):
        res = self.run_lazy("help")
        self.assertIn("usage:", res.stdout)
        self.assertIn("Commands:", res.stdout)

if __name__ == "__main__":
    unittest.main()
