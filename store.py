"""JSONL-backed task store, synced via git.

Replaces the old SQLite db.py. The repo path holds a clone of a private
gist; tasks live in tasks.jsonl, one JSON object per line.

Reads pull (with a freshness window). Writes pull, mutate, commit, push.
On push reject, retry with pull --rebase. Conflicts surface to stderr.
"""

import fcntl
import json
import re
import os
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

import git_ops

TASKS_FILE = 'tasks.jsonl'
DEFAULT_REPO = os.path.expanduser('~/.local/share/lazy/repo')
DEFAULT_FRESHNESS = 30
DEFAULT_AUTO_PUSH = True
_PUSH_FAILURE_THRESHOLD = 10


class StoreNotInitialized(Exception):
    """Raised when no repo is configured and no LAZY_HOME override is set."""


class StoreConflicted(Exception):
    """Raised when tasks.jsonl still holds unresolved conflict markers."""


def _iso(d):
    return d.isoformat() if hasattr(d, 'isoformat') else d


def _utcnow():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _warn(msg):
    sys.stderr.write(f"lazy: {msg}\n")


class Store:
    def __init__(self, repo_path, auto_push=True, pull_freshness=DEFAULT_FRESHNESS,
                 no_remote=False):
        self.path = repo_path
        self.tasks_path = os.path.join(repo_path, TASKS_FILE)
        self.auto_push = auto_push and not no_remote
        self.pull_freshness = pull_freshness
        self.no_remote = no_remote
        # Inside .git/: the parent dir is shared (every LAZY_HOME under /tmp
        # collided on one sentinel and one failure counter).
        self._state_dir = os.path.join(repo_path, '.git')
        self._sentinel = os.path.join(self._state_dir, 'lazy-last-pull')

    # ---- sync internals ----

    def _touch_sentinel(self):
        try:
            open(self._sentinel, 'w').close()
        except OSError:
            pass

    def _push_failures_path(self):
        return os.path.join(self._state_dir, 'lazy-push-failures')

    def _record_push(self, ok):
        """Track consecutive push failures so we can warn once after a long
        run of silent failures (e.g., gist deleted, auth expired). Lazy ethos
        keeps us silent in the common case; this only fires when the system
        has been failing for long enough that the user should know."""
        path = self._push_failures_path()
        try:
            with open(path) as f:
                count = int((f.read().strip() or '0'))
        except (FileNotFoundError, ValueError, OSError):
            count = 0
        count = 0 if ok else count + 1
        # Re-warn every N failures, not once ever: `== threshold` meant a gist
        # that stayed unreachable went permanently silent after one line.
        if count >= _PUSH_FAILURE_THRESHOLD and count % _PUSH_FAILURE_THRESHOLD == 0:
            sys.stderr.write(
                f"lazy: push has failed {count} consecutive times. "
                "Network down? Gist deleted? Run `lazy backend` to inspect.\n"
            )
        try:
            with open(path, 'w') as f:
                f.write(str(count))
        except OSError:
            pass

    def _attempt_push(self):
        """Push, retry-on-reject via pull-rebase, record outcome.

        A rebase that stops on a conflict must be aborted, not left in place:
        mid-rebase HEAD is detached, so every later write would commit off the
        branch, be unreachable from main, and be discarded by the eventual
        abort -- silent data loss. Aborting keeps the local commits and lets
        the next invocation retry.
        """
        ok, _ = git_ops.push(self.path)
        if not ok:
            r_ok, _ = git_ops.pull_rebase(self.path)
            if r_ok:
                ok, _ = git_ops.push(self.path)
            elif git_ops.rebase_in_progress(self.path):
                git_ops.rebase_abort(self.path)
                _warn("sync conflict: rebase aborted, your local tasks are intact. "
                      "Both sides changed the same task; run `lazy sync` to retry.")
        self._record_push(ok)
        return ok

    def _ensure_synced(self, force_pull=False):
        """Bring local and origin into agreement. Silent on failure (lazy ethos).

        - If the working tree has been left dirty (e.g., a previous invocation
          was killed mid-commit), commit the orphan so we operate on a clean
          base without losing it.
        - If local has unpushed commits, flush them (with rebase retry).
        - Otherwise, pull if forced (writes always force) or freshness expired.

        On any network or rebase failure: stay silent, leave state as-is, try
        again next invocation. The user is never asked to do anything. After
        N consecutive push failures we surface ONE warning (see _record_push).
        """
        if self.no_remote or not git_ops.has_remote(self.path):
            return
        # A repo left mid-rebase by an earlier interrupted run is unusable: the
        # documented recovery ("resolve, then `lazy sync`") cannot work from a
        # detached HEAD. Recover it here instead of writing into the wedge.
        if git_ops.rebase_in_progress(self.path):
            git_ops.rebase_abort(self.path)
            _warn("recovered a repo left mid-rebase; local tasks are intact.")
        if git_ops.is_dirty(self.path):
            # Commit the orphan, never stash it. Stashing hid a real task that
            # a failed commit had left in the working tree: the user was told
            # "Added", and the next invocation moved it somewhere no lazy
            # command lists. A dirty tasks.jsonl is valid content, not debris.
            ok, err = git_ops.add_and_commit(
                self.path, TASKS_FILE, 'lazy: recovered orphaned write')
            if not ok:
                _warn(f"could not commit recovered write ({err})")
        if git_ops.unpushed_count(self.path) > 0:
            self._attempt_push()
            self._touch_sentinel()
            return
        if not force_pull:
            try:
                if time.time() - os.path.getmtime(self._sentinel) < self.pull_freshness:
                    return
            except FileNotFoundError:
                pass
        git_ops.pull_ff(self.path)
        self._touch_sentinel()

    def _commit_and_push(self, message):
        ok, err = git_ops.add_and_commit(self.path, TASKS_FILE, message)
        if not ok:
            _warn(f"commit failed ({err})")
            return
        if not self.auto_push or not git_ops.has_remote(self.path):
            return
        # Same retry-on-reject path as _ensure_synced; both go through
        # _attempt_push so failure tracking is unified.
        self._attempt_push()

    # ---- file IO ----

    def _read(self):
        try:
            with open(self.tasks_path) as f:
                lines = f.readlines()
        except FileNotFoundError:
            return []
        # Conflict markers are not JSON, so the loop below would skip them and
        # happily parse BOTH sides of the conflict -- silently duplicating every
        # task in it. Refuse instead.
        if any(l.startswith(('<<<<<<<', '=======', '>>>>>>>')) for l in lines):
            raise StoreConflicted(
                f"{self.tasks_path} has unresolved conflict markers. "
                "Edit it to keep the lines you want, then run `lazy sync`."
            )
        tasks = []
        # Lines we cannot interpret are carried through the read-modify-write
        # cycle verbatim. Dropping them from this list used to DELETE them on
        # the next write -- a truncated line (power loss mid-write) or a
        # hand-edited gist line was destroyed by the very next `lazy add`.
        self._passthrough = []
        for n, line in enumerate(lines, start=1):
            raw = line.rstrip('\n')
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                _warn(f"preserving unparseable line {n} of tasks.jsonl: {e}")
                self._passthrough.append(raw)
                continue
            if 'id' not in obj:
                self._passthrough.append(raw)  # metadata / future schema lines
                continue
            tasks.append(obj)
        return tasks

    def _write(self, tasks):
        tasks = sorted(tasks, key=lambda t: t['id'])
        directory = os.path.dirname(self.tasks_path)
        os.makedirs(directory, exist_ok=True)
        # Per-process temp name: a single shared `tasks.jsonl.tmp` let two
        # writers truncate each other's file, and the winner of the rename was
        # not the one that reported success.
        fd, tmp = tempfile.mkstemp(dir=directory, prefix='.tasks-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w') as f:
                for raw in getattr(self, '_passthrough', []):
                    f.write(raw + '\n')
                for t in tasks:
                    f.write(json.dumps(t, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())   # os.replace is atomic, not durable
            os.replace(tmp, self.tasks_path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        dir_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dir_fd)           # make the rename itself survive power loss
        finally:
            os.close(dir_fd)

    # ---- public API (mirrors old db.py shape) ----

    @contextmanager
    def _locked(self):
        """Serialize the whole read-mutate-write cycle across processes.

        The CLI and the MCP server both write, and two Claude Code sessions
        each run their own server -- without this, two interleaved writes both
        report success and the second one's whole-file rewrite silently drops
        the first one's task. Degrades to unlocked if the lock cannot be taken:
        a backlog tool must never refuse to work.
        """
        handle = None
        try:
            handle = open(os.path.join(self.path, '.git', 'lazy.lock'), 'w')
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except OSError:
            if handle:
                handle.close()
            handle = None
        try:
            yield
        finally:
            if handle:
                handle.close()   # releases the flock

    @contextmanager
    def _writing(self, message):
        """Read-mutate-write-commit-push lifecycle for any mutation. The
        message can be a string or a callable evaluated after the mutation
        (so commit messages can include counts computed during the mutation).
        add_and_commit is a no-op when the file content didn't actually
        change, so methods that find nothing to do incur a wasted file
        rewrite but no spurious commit."""
        with self._locked():
            self._ensure_synced(force_pull=True)
            tasks = self._read()
            yield tasks
            self._write(tasks)
            self._commit_and_push(message() if callable(message) else message)

    def get_tasks(self, mode):
        self._ensure_synced()
        tasks = [t for t in self._read() if t.get('status') == 'pending']
        if mode == 'today':
            today = date.today().isoformat()
            tasks = [t for t in tasks if t.get('due_date', '') <= today]
        return sorted(tasks, key=lambda t: (t.get('due_date', ''), t['id']))

    def get_task(self, task_id):
        self._ensure_synced()
        return next((t for t in self._read() if t['id'] == task_id), None)

    def add_task(self, description, due_date):
        with self._writing(f"add: {description}") as tasks:
            seen = [t['id'] for t in tasks]
            for raw in getattr(self, '_passthrough', []):
                m = re.search(r'"id"\s*:\s*(\d+)', raw)
                if m:
                    seen.append(int(m.group(1)))
            new_id = max(seen, default=0) + 1
            tasks.append({
                'id': new_id,
                'description': description,
                'due_date': _iso(due_date),
                'status': 'pending',
                'created_at': _utcnow(),
            })
        return new_id

    def complete_task(self, task_id):
        with self._writing(f"done: {task_id}") as tasks:
            for t in tasks:
                if t['id'] == task_id:
                    t['status'] = 'done'
                    return

    def delete_task(self, task_id):
        # Exactly one, to match complete/move: offline adds on two machines can
        # mint the same id, and deleting "all matches" took the innocent twin.
        with self._writing(f"rm: {task_id}") as tasks:
            for i, t in enumerate(tasks):
                if t['id'] == task_id:
                    del tasks[i]
                    return

    def move_task(self, task_id, new_date):
        new_iso = _iso(new_date)
        with self._writing(f"move: {task_id} -> {new_iso}") as tasks:
            for t in tasks:
                if t['id'] == task_id:
                    t['due_date'] = new_iso
                    return

    def rename_task(self, task_id, new_description):
        found = False
        with self._writing(f"rename: {task_id} -> {new_description}") as tasks:
            for t in tasks:
                if t['id'] == task_id:
                    t['description'] = new_description
                    found = True
                    break
        if not found:
            raise ValueError(f"Task {task_id} not found.")

    def push_tasks(self):
        from_iso = _iso(date.today())
        to_iso = _iso(date.today() + timedelta(days=1))
        moved = 0
        with self._writing(lambda: f"push: {moved} task(s) -> {to_iso}") as tasks:
            for t in tasks:
                if t.get('status') == 'pending' and t.get('due_date', '') <= from_iso:
                    t['due_date'] = to_iso
                    moved += 1
        return moved

    # ---- sync utility ----

    def sync(self):
        """Pull (rebasing if needed) + push. Used by `lazy sync`."""
        if self.no_remote or not git_ops.has_remote(self.path):
            _warn("no remote configured; nothing to sync")
            return
        ok, err = git_ops.pull_rebase(self.path)
        if not ok:
            _warn(f"pull/rebase failed ({err})")
            _warn(f"  resolve in {self.path}/{TASKS_FILE} then run `lazy sync` again")
            return
        ok, err = git_ops.push(self.path)
        if not ok:
            _warn(f"push failed ({err})")


# ---- factory ----

def _read_user_config():
    path = os.path.expanduser('~/.config/lazy/config.json')
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def open_store():
    """Resolve config (env > user config > defaults) and return a Store."""
    home_override = os.environ.get('LAZY_HOME')
    no_remote = os.environ.get('LAZY_NO_REMOTE') == '1'

    if home_override:
        repo_path = os.path.expanduser(home_override)
        if not git_ops.is_repo(repo_path):
            raise StoreNotInitialized(
                f"LAZY_HOME={home_override} is not a git repo. Point it at a "
                f"lazy clone, or unset it to use the configured store."
            )
        return Store(repo_path, auto_push=not no_remote, no_remote=no_remote)

    cfg = _read_user_config()
    repo_path = os.path.expanduser(cfg.get('repo_path', DEFAULT_REPO))
    if not git_ops.is_repo(repo_path):
        raise StoreNotInitialized(
            f"lazy is not initialized. Run `lazy init` (or `lazy init --from-gist <id>` "
            f"on additional machines)."
        )
    return Store(
        repo_path,
        auto_push=cfg.get('auto_push', DEFAULT_AUTO_PUSH),
        pull_freshness=cfg.get('pull_freshness_seconds', DEFAULT_FRESHNESS),
        no_remote=no_remote,
    )
