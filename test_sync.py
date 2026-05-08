"""Integration tests for the sync layer.

Wires up a real bare git repo as 'origin' and a real working clone as the
lazy home. No mocks — exercises the actual subprocess paths through git_ops
and Store. Catches the class of bug where lazy *appears* to work in
isolation but fails to push to a real remote.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _git(args, cwd, check=True):
    return subprocess.run(['git'] + args, cwd=cwd, capture_output=True,
                          text=True, check=check)


def _set_identity(path):
    _git(['config', 'user.email', 'test@example.com'], cwd=path)
    _git(['config', 'user.name', 'Test'], cwd=path)


class StoreWithRemote(unittest.TestCase):
    """Working clone backed by a real bare repo. Push/pull actually work."""

    def setUp(self):
        self.remote_path = tempfile.mkdtemp(prefix='lazy-remote-')
        _git(['init', '-q', '--bare', '-b', 'main'], cwd=self.remote_path)

        self.repo_path = tempfile.mkdtemp(prefix='lazy-test-')
        _git(['init', '-q', '-b', 'main'], cwd=self.repo_path)
        _set_identity(self.repo_path)
        _git(['remote', 'add', 'origin', self.remote_path], cwd=self.repo_path)

        with open(os.path.join(self.repo_path, 'tasks.jsonl'), 'w') as f:
            f.write('{"_init": true}\n')
        _git(['add', 'tasks.jsonl'], cwd=self.repo_path)
        _git(['commit', '-q', '-m', 'init'], cwd=self.repo_path)
        _git(['push', '-q', '-u', 'origin', 'main'], cwd=self.repo_path)

        os.environ['LAZY_HOME'] = self.repo_path
        os.environ.pop('LAZY_NO_REMOTE', None)

    def tearDown(self):
        os.environ.pop('LAZY_HOME', None)
        shutil.rmtree(self.repo_path, ignore_errors=True)
        shutil.rmtree(self.remote_path, ignore_errors=True)

    def remote_tasks(self):
        """tasks.jsonl as it currently exists on origin."""
        result = _git(['show', 'main:tasks.jsonl'], cwd=self.remote_path)
        out = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if 'id' in obj:
                out.append(obj)
        return out

    def local_unpushed(self):
        result = _git(['rev-list', '--count', '@{u}..HEAD'], cwd=self.repo_path)
        return int(result.stdout.strip())


class TestHasRemote(StoreWithRemote):
    """Regression: git_ops.has_remote() returned False even when origin existed,
    because git_ops._run() returned stderr (always empty on success), and
    has_remote treated that as 'no URL configured'."""

    def test_has_remote_is_true_when_origin_is_configured(self):
        import git_ops
        self.assertTrue(
            git_ops.has_remote(self.repo_path),
            "has_remote must return True for a clone with origin configured"
        )


class TestWritesAutoPush(StoreWithRemote):
    """Every mutation lands on origin without the user doing anything."""

    def test_add_pushes_to_origin(self):
        from store import open_store
        store = open_store()
        store.add_task("hello", date.today())
        descs = [t['description'] for t in self.remote_tasks()]
        self.assertIn("hello", descs)
        self.assertEqual(self.local_unpushed(), 0)

    def test_complete_pushes_to_origin(self):
        from store import open_store
        store = open_store()
        tid = store.add_task("done me", date.today())
        store.complete_task(tid)
        match = next(t for t in self.remote_tasks() if t['id'] == tid)
        self.assertEqual(match['status'], 'done')
        self.assertEqual(self.local_unpushed(), 0)

    def test_rename_pushes_to_origin(self):
        from store import open_store
        store = open_store()
        tid = store.add_task("orig", date.today())
        store.rename_task(tid, "renamed")
        match = next(t for t in self.remote_tasks() if t['id'] == tid)
        self.assertEqual(match['description'], "renamed")
        self.assertEqual(self.local_unpushed(), 0)

    def test_delete_pushes_to_origin(self):
        from store import open_store
        store = open_store()
        tid = store.add_task("ephemeral", date.today())
        store.delete_task(tid)
        ids = [t['id'] for t in self.remote_tasks()]
        self.assertNotIn(tid, ids)
        self.assertEqual(self.local_unpushed(), 0)


class TestReadsFlushPendingCommits(StoreWithRemote):
    """Lazy ethos: a read after a transient push failure heals silently."""

    def test_read_after_offline_write_flushes_pending_to_origin(self):
        from store import Store
        # Simulate a write whose push didn't happen (transient network).
        offline = Store(self.repo_path, no_remote=True)
        offline.add_task("offline-add", date.today())
        self.assertNotIn(
            "offline-add",
            [t['description'] for t in self.remote_tasks()],
        )
        self.assertEqual(self.local_unpushed(), 1)

        # The next read with sync enabled should auto-push the pending commit.
        online = Store(self.repo_path, auto_push=True, pull_freshness=0)
        online.get_tasks('all')

        self.assertIn(
            "offline-add",
            [t['description'] for t in self.remote_tasks()],
        )
        self.assertEqual(self.local_unpushed(), 0)


class TestPushRejectIsHandled(StoreWithRemote):
    """Two machines racing: B pushes after A, B's push is rejected, B rebases
    and retries. Both writes must land on origin."""

    def test_concurrent_writes_both_land_via_rebase(self):
        from store import Store
        other_path = tempfile.mkdtemp(prefix='lazy-other-')
        # Reuse parent's bare remote, second working clone
        _git(['init', '-q', '-b', 'main'], cwd=other_path)
        _set_identity(other_path)
        _git(['remote', 'add', 'origin', self.remote_path], cwd=other_path)
        _git(['fetch', '-q', 'origin'], cwd=other_path)
        _git(['checkout', '-q', '-b', 'main', 'origin/main'], cwd=other_path,
             check=False)  # may already exist depending on git version
        _git(['branch', '--set-upstream-to=origin/main', 'main'], cwd=other_path)
        try:
            # Machine A writes and pushes
            store_a = Store(self.repo_path, auto_push=True, pull_freshness=0)
            store_a.add_task("A-task", date.today())
            self.assertIn("A-task",
                          [t['description'] for t in self.remote_tasks()])

            # Machine B (still at the seed commit) writes; its push should
            # be rejected, triggering pull-rebase + retry.
            store_b = Store(other_path, auto_push=True, pull_freshness=0)
            store_b.add_task("B-task", date.today())

            descs = [t['description'] for t in self.remote_tasks()]
            self.assertIn("A-task", descs)
            self.assertIn("B-task", descs)
        finally:
            shutil.rmtree(other_path, ignore_errors=True)


class TestNoRemoteIsSilent(unittest.TestCase):
    """Single-machine fallback: a repo with no origin doesn't error on any
    operation. Sync is a no-op."""

    def setUp(self):
        self.repo_path = tempfile.mkdtemp(prefix='lazy-noremote-')
        _git(['init', '-q', '-b', 'main'], cwd=self.repo_path)
        _set_identity(self.repo_path)
        os.environ['LAZY_HOME'] = self.repo_path
        os.environ.pop('LAZY_NO_REMOTE', None)

    def tearDown(self):
        os.environ.pop('LAZY_HOME', None)
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def test_add_without_remote_works(self):
        from store import open_store
        store = open_store()
        tid = store.add_task("local-only", date.today())
        self.assertEqual(store.get_task(tid)['description'], "local-only")

    def test_get_tasks_without_remote_works(self):
        from store import open_store
        store = open_store()
        store.add_task("a", date.today())
        store.add_task("b", date.today())
        descs = {t['description'] for t in store.get_tasks('all')}
        self.assertEqual(descs, {"a", "b"})


if __name__ == "__main__":
    unittest.main()
