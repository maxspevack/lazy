"""End-to-end CLI tests via subprocess. Slow but exercises argparse + dispatch."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import date, timedelta


def _setup_repo(path):
    subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=path, check=True)
    subprocess.run(['git', 'config', 'user.email', 'test@example.com'], cwd=path, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=path, check=True)


class TestLazyCLI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lazy_bin = os.path.join(os.path.dirname(__file__), 'lazy')

    def setUp(self):
        self.repo_path = tempfile.mkdtemp(prefix='lazy-cli-test-')
        _setup_repo(self.repo_path)
        self.env = {
            **os.environ,
            'LAZY_HOME': self.repo_path,
            'LAZY_NO_REMOTE': '1',
        }

    def tearDown(self):
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def run_lazy(self, *args):
        return subprocess.run(
            [self.lazy_bin] + list(args),
            capture_output=True, text=True, env=self.env
        )

    def read_tasks(self):
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

    def latest_id(self, description):
        for t in reversed(self.read_tasks()):
            if t['description'] == description:
                return t['id']
        return None

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
        descs = [t['description'] for t in self.read_tasks()]
        self.assertIn("fold laundry", descs)
        for d in descs:
            self.assertFalse(d.endswith(" on"), f"preposition not stripped: {d!r}")

    def test_done_marks_complete(self):
        self.run_lazy("a", "kill it", "today")
        tid = self.latest_id("kill it")
        self.run_lazy("d", str(tid))
        task = next(t for t in self.read_tasks() if t['id'] == tid)
        self.assertEqual(task['status'], 'done')

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
        # Seed an overdue task by writing tasks.jsonl directly
        path = os.path.join(self.repo_path, 'tasks.jsonl')
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        with open(path, 'w') as f:
            f.write(json.dumps({
                'id': 1,
                'description': 'late',
                'due_date': yesterday,
                'status': 'pending',
                'created_at': '2026-01-01T00:00:00Z',
            }) + '\n')
        # Commit so the store sees a clean state
        subprocess.run(['git', 'add', 'tasks.jsonl'], cwd=self.repo_path, check=True)
        subprocess.run(['git', 'commit', '-q', '-m', 'seed'], cwd=self.repo_path, check=True)

        self.run_lazy("b", "1")
        task = next(t for t in self.read_tasks() if t['id'] == 1)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertEqual(task['due_date'], tomorrow)

    def test_help_alias(self):
        out = self.run_lazy("help").stdout
        self.assertIn("usage:", out)
        self.assertIn("Commands:", out)

    def test_help_does_not_create_task(self):
        """RELEASE_NOTES claims this was fixed in v2026.04.27."""
        self.run_lazy("a", "seed", "today")
        self.run_lazy("help")
        descs = [t['description'] for t in self.read_tasks()]
        self.assertNotIn("help", descs)
        self.assertEqual(len(descs), 1)


if __name__ == "__main__":
    unittest.main()
