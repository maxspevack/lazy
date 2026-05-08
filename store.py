"""JSONL-backed task store, synced via git.

Replaces the old SQLite db.py. The repo path holds a clone of a private
gist; tasks live in tasks.jsonl, one JSON object per line.

Reads pull (with a freshness window). Writes pull, mutate, commit, push.
On push reject, retry with pull --rebase. Conflicts surface to stderr.
"""

import json
import os
import sys
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
        self._sentinel = os.path.join(os.path.dirname(repo_path) or '.', '.last-pull')

    # ---- sync internals ----

    def _touch_sentinel(self):
        try:
            open(self._sentinel, 'w').close()
        except OSError:
            pass

    def _push_failures_path(self):
        return os.path.join(os.path.dirname(self.path) or '.', '.push-failures')

    def _record_push(self, ok):
        """Track consecutive push failures so we can warn once after a long
        run of silent failures (e.g., gist deleted, auth expired). Lazy ethos
        keeps us silent in the common case; this only fires when the system
        has been failing for long enough that the user should know."""
        path = self._push_failures_path()
        try:
            with open(path) as f:
                count = int((f.read().strip() or '0'))
        except (FileNotFoundError, ValueError):
            count = 0
        count = 0 if ok else count + 1
        if count == _PUSH_FAILURE_THRESHOLD:
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
        """Push, retry-on-reject via pull-rebase, record outcome."""
        ok, _ = git_ops.push(self.path)
        if not ok:
            r_ok, _ = git_ops.pull_rebase(self.path)
            if r_ok:
                ok, _ = git_ops.push(self.path)
        self._record_push(ok)
        return ok

    def _ensure_synced(self, force_pull=False):
        """Bring local and origin into agreement. Silent on failure (lazy ethos).

        - If the working tree has been left dirty (e.g., a previous invocation
          was killed mid-commit), stash the orphan so we operate on a clean
          base.
        - If local has unpushed commits, flush them (with rebase retry).
        - Otherwise, pull if forced (writes always force) or freshness expired.

        On any network or rebase failure: stay silent, leave state as-is, try
        again next invocation. The user is never asked to do anything. After
        N consecutive push failures we surface ONE warning (see _record_push).
        """
        if self.no_remote or not git_ops.has_remote(self.path):
            return
        if git_ops.is_dirty(self.path):
            git_ops.stash(self.path)
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
        tasks = []
        for n, line in enumerate(lines, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                _warn(f"skipping malformed line {n} of tasks.jsonl: {e}")
                continue
            if 'id' not in obj:
                continue  # metadata / future schema lines, silently ignored
            tasks.append(obj)
        return tasks

    def _write(self, tasks):
        tasks = sorted(tasks, key=lambda t: t['id'])
        tmp = self.tasks_path + '.tmp'
        os.makedirs(os.path.dirname(self.tasks_path), exist_ok=True)
        with open(tmp, 'w') as f:
            for t in tasks:
                f.write(json.dumps(t, ensure_ascii=False) + '\n')
        os.replace(tmp, self.tasks_path)

    # ---- public API (mirrors old db.py shape) ----

    @contextmanager
    def _writing(self, message):
        """Read-mutate-write-commit-push lifecycle for any mutation. The
        message can be a string or a callable evaluated after the mutation
        (so commit messages can include counts computed during the mutation).
        add_and_commit is a no-op when the file content didn't actually
        change, so methods that find nothing to do incur a wasted file
        rewrite but no spurious commit."""
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
            tasks = [t for t in tasks if t['due_date'] <= today]
        return sorted(tasks, key=lambda t: (t['due_date'], t['id']))

    def get_task(self, task_id):
        self._ensure_synced()
        return next((t for t in self._read() if t['id'] == task_id), None)

    def add_task(self, description, due_date):
        with self._writing(f"add: {description}") as tasks:
            new_id = max((t['id'] for t in tasks), default=0) + 1
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
        with self._writing(f"rm: {task_id}") as tasks:
            tasks[:] = [t for t in tasks if t['id'] != task_id]

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

    def push_tasks(self, from_date=None, to_date=None):
        from_iso = _iso(from_date or date.today())
        to_iso = _iso(to_date or (date.today() + timedelta(days=1)))
        moved = 0
        with self._writing(lambda: f"push: {moved} task(s) -> {to_iso}") as tasks:
            for t in tasks:
                if t.get('status') == 'pending' and t['due_date'] <= from_iso:
                    t['due_date'] = to_iso
                    moved += 1
        return moved

    def unpushed_count(self):
        """Local commits not yet on origin. Used by the CLI to warn."""
        if self.no_remote or not git_ops.has_remote(self.path):
            return 0
        return git_ops.unpushed_count(self.path)

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
