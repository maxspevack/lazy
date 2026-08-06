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


_GIT_FLOOR = (2, 34)  # Behavior guarantees from 2.34+: pull.rebase warning,
                       # init.defaultBranch=main, deterministic rev-list output.


def _git_version():
    out = subprocess.run(['git', '--version'], capture_output=True,
                         text=True, check=True).stdout
    parts = out.split()[2].split('.')
    return tuple(int(p) for p in parts[:2])


def _git(args, cwd, check=True):
    return subprocess.run(['git'] + args, cwd=cwd, capture_output=True,
                          text=True, check=check)


def _set_identity(path):
    _git(['config', 'user.email', 'test@example.com'], cwd=path)
    _git(['config', 'user.name', 'Test'], cwd=path)


def setUpModule():
    """CIQ standard: same-source-same-toolchain-same-output. Tests assume
    git >= 2.34 for pull.rebase, default-branch, and rev-list semantics."""
    version = _git_version()
    if version < _GIT_FLOOR:
        raise unittest.SkipTest(
            f"git {version[0]}.{version[1]} below floor {_GIT_FLOOR[0]}.{_GIT_FLOOR[1]}"
        )


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


class TestDirtyWorkingTreeRecovery(StoreWithRemote):
    """If a previous invocation was killed mid-commit, the next operation
    must self-clean rather than refuse or corrupt."""

    def test_orphaned_staged_change_is_preserved_not_discarded(self):
        from store import Store
        # Simulate kill between `git add` and `git commit`: write to the
        # working tree and stage it, but don't commit.
        path = os.path.join(self.repo_path, 'tasks.jsonl')
        with open(path, 'w') as f:
            f.write('{"id":99,"description":"orphan","due_date":"2026-01-01",'
                    '"status":"pending","created_at":"2026-01-01T00:00:00Z"}\n')
        _git(['add', 'tasks.jsonl'], cwd=self.repo_path)

        # Next operation should not crash and should leave a clean tree.
        store = Store(self.repo_path, auto_push=True, pull_freshness=0)
        store.add_task("post-orphan", date.today())

        result = _git(['status', '--porcelain'], cwd=self.repo_path)
        self.assertEqual(result.stdout.strip(), '',
                         "working tree must be clean after self-recovery")
        descs = [t['description'] for t in self.remote_tasks()]
        self.assertIn("post-orphan", descs)
        # The orphan was a real task the user was told had been added. It must
        # survive recovery -- stashing it made it invisible to every command.
        self.assertIn("orphan", descs,
                      "orphaned write must be recovered, not discarded")

    def test_unstaged_dirty_file_does_not_block_operation(self):
        from store import Store
        # Simulate manual edit of tasks.jsonl that wasn't committed.
        path = os.path.join(self.repo_path, 'tasks.jsonl')
        with open(path, 'w') as f:
            f.write('{"id":50,"description":"manual","due_date":"2026-01-01",'
                    '"status":"pending","created_at":"2026-01-01T00:00:00Z"}\n')

        store = Store(self.repo_path, auto_push=True, pull_freshness=0)
        store.add_task("after-manual", date.today())

        result = _git(['status', '--porcelain'], cwd=self.repo_path)
        self.assertEqual(result.stdout.strip(), '')


class TestSameTaskConflict(StoreWithRemote):
    """Two clones rename the same task to different strings. One push wins;
    the other rebases or surfaces, never silently discards."""

    def test_concurrent_renames_one_wins_neither_corrupts(self):
        from store import Store
        # Seed a shared task on origin
        store_a = Store(self.repo_path, auto_push=True, pull_freshness=0)
        tid = store_a.add_task("shared", date.today())

        # Set up second clone, which must have the seed commit
        other_path = tempfile.mkdtemp(prefix='lazy-other-')
        _git(['init', '-q', '-b', 'main'], cwd=other_path)
        _set_identity(other_path)
        _git(['remote', 'add', 'origin', self.remote_path], cwd=other_path)
        _git(['fetch', '-q', 'origin'], cwd=other_path)
        _git(['checkout', '-q', '-b', 'main', 'origin/main'], cwd=other_path,
             check=False)
        _git(['branch', '--set-upstream-to=origin/main', 'main'], cwd=other_path)
        try:
            store_b = Store(other_path, auto_push=True, pull_freshness=0)

            # Both rename to different strings; A pushes first.
            store_a.rename_task(tid, "A-rename")
            store_b.rename_task(tid, "B-rename")

            # Origin must have exactly one of the two renames; whichever B's
            # rebase landed on should be the surviving description.
            tasks = self.remote_tasks()
            shared = [t for t in tasks if t['id'] == tid]
            self.assertEqual(len(shared), 1, "task must not be duplicated")
            self.assertIn(shared[0]['description'], ("A-rename", "B-rename"))
        finally:
            shutil.rmtree(other_path, ignore_errors=True)


class TestPushFailureCap(unittest.TestCase):
    """After N consecutive push failures, surface exactly one stderr warning."""

    def setUp(self):
        # Working clone pointing at a remote that doesn't exist
        self.repo_path = tempfile.mkdtemp(prefix='lazy-failtest-')
        _git(['init', '-q', '-b', 'main'], cwd=self.repo_path)
        _set_identity(self.repo_path)
        _git(['remote', 'add', 'origin', '/nonexistent/dead-remote.git'],
             cwd=self.repo_path)
        with open(os.path.join(self.repo_path, 'tasks.jsonl'), 'w') as f:
            f.write('{"_init": true}\n')
        _git(['add', 'tasks.jsonl'], cwd=self.repo_path)
        _git(['commit', '-q', '-m', 'init'], cwd=self.repo_path)
        os.environ['LAZY_HOME'] = self.repo_path
        os.environ.pop('LAZY_NO_REMOTE', None)

    def tearDown(self):
        os.environ.pop('LAZY_HOME', None)
        shutil.rmtree(self.repo_path, ignore_errors=True)

    def test_warning_fires_exactly_at_threshold(self):
        from store import Store, _PUSH_FAILURE_THRESHOLD
        from io import StringIO
        import contextlib

        store = Store(self.repo_path, auto_push=True, pull_freshness=0)
        # Drive _attempt_push directly so we don't depend on which other
        # methods happen to push.
        for i in range(_PUSH_FAILURE_THRESHOLD - 1):
            buf = StringIO()
            with contextlib.redirect_stderr(buf):
                store._attempt_push()
            self.assertEqual(
                buf.getvalue(), '',
                f"warning fired prematurely at attempt {i+1}",
            )

        # The Nth failure should produce exactly one warning line
        buf = StringIO()
        with contextlib.redirect_stderr(buf):
            store._attempt_push()
        self.assertIn("push has failed", buf.getvalue())
        self.assertIn(f"{_PUSH_FAILURE_THRESHOLD} consecutive", buf.getvalue())

    def test_counter_resets_on_success(self):
        from store import Store
        store = Store(self.repo_path, auto_push=True, pull_freshness=0)
        # Drive a few failures
        for _ in range(3):
            store._attempt_push()
        # Manually record success and verify the counter is back to zero
        store._record_push(ok=True)
        with open(store._push_failures_path()) as f:
            self.assertEqual(f.read().strip(), '0')


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




class TestRebaseConflictRecovery(StoreWithRemote):
    """The branch that had zero coverage: a genuinely divergent push that gets
    rejected, rebases, and CONFLICTS. The existing conflict tests cannot reach
    it -- _writing force-pulls before every mutation, so the second writer is
    always current and its push is never rejected."""

    def _second_clone(self):
        path = tempfile.mkdtemp(prefix='lazy-cloneb-')
        _git(['clone', '-q', self.remote_path, path], cwd=os.path.dirname(path))
        _set_identity(path)
        self.addCleanup(shutil.rmtree, path, ignore_errors=True)
        return path

    def test_conflicting_divergence_leaves_a_usable_repo(self):
        from store import Store
        a = Store(self.repo_path, auto_push=True, pull_freshness=0)
        tid = a.add_task("original", date.today())

        b_path = self._second_clone()
        # B goes offline and edits the same task A is about to edit.
        offline_b = Store(b_path, auto_push=False, pull_freshness=0, no_remote=True)
        offline_b.rename_task(tid, "B version")

        a.rename_task(tid, "A version")   # A wins the race to origin

        # B comes back online with an unpushed commit against an advanced origin:
        # push rejected -> pull --rebase -> conflict on the same line.
        b = Store(b_path, auto_push=True, pull_freshness=0)
        b.get_tasks('all')

        head = _git(['symbolic-ref', '-q', 'HEAD'], cwd=b_path, check=False)
        self.assertEqual(head.returncode, 0,
                         "HEAD must stay on a branch; a detached HEAD sends every "
                         "later write to a commit no push will ever deliver")
        status = _git(['status', '--porcelain'], cwd=b_path)
        self.assertNotIn('UU', status.stdout,
                         "no unresolved conflict may be left in the working tree")
        # B's own work is still reachable from its branch.
        log = _git(['log', '--oneline', '-20'], cwd=b_path).stdout
        self.assertIn("B version", log, "B's local commit must survive recovery")


if __name__ == "__main__":
    unittest.main()
