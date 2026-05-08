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
from datetime import date, datetime, timedelta, timezone

import git_ops

TASKS_FILE = 'tasks.jsonl'
DEFAULT_REPO = os.path.expanduser('~/.local/share/lazy/repo')
DEFAULT_FRESHNESS = 30
DEFAULT_AUTO_PUSH = True


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

    def _ensure_synced(self, force_pull=False):
        """Bring local and origin into agreement. Silent on failure (lazy ethos).

        - If local has unpushed commits, push them (with pull-rebase retry on
          reject). Origin is the canonical state; pending local commits are a
          temporary anomaly we silently flush whenever we touch the network.
        - Otherwise, pull if forced (writes always force) or if the freshness
          window has expired.

        On any network or rebase failure: stay silent, leave state as-is, try
        again next invocation. The user is never asked to do anything.
        """
        if self.no_remote or not git_ops.has_remote(self.path):
            return
        if git_ops.unpushed_count(self.path) > 0:
            ok, _ = git_ops.push(self.path)
            if not ok:
                ok, _ = git_ops.pull_rebase(self.path)
                if ok:
                    git_ops.push(self.path)
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
        ok, _ = git_ops.push(self.path)
        if ok:
            return
        # Push rejected — origin moved while we were writing. Rebase, retry.
        ok, _ = git_ops.pull_rebase(self.path)
        if ok:
            git_ops.push(self.path)
        # Stay silent on remaining failures; next op will re-attempt.

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

    def get_tasks(self, mode):
        self._ensure_synced()
        tasks = [t for t in self._read() if t.get('status') == 'pending']
        if mode == 'today':
            today = date.today().isoformat()
            tasks = [t for t in tasks if t['due_date'] <= today]
        return sorted(tasks, key=lambda t: (t['due_date'], t['id']))

    def get_task(self, task_id):
        self._ensure_synced()
        for t in self._read():
            if t['id'] == task_id:
                return t
        return None

    def add_task(self, description, due_date):
        self._ensure_synced(force_pull=True)
        tasks = self._read()
        new_id = max((t['id'] for t in tasks), default=0) + 1
        tasks.append({
            'id': new_id,
            'description': description,
            'due_date': _iso(due_date),
            'status': 'pending',
            'created_at': _utcnow(),
        })
        self._write(tasks)
        self._commit_and_push(f"add: {description}")
        return new_id

    def complete_task(self, task_id):
        self._mutate(task_id, {'status': 'done'}, f"done: {task_id}")

    def delete_task(self, task_id):
        self._ensure_synced(force_pull=True)
        tasks = self._read()
        before = len(tasks)
        tasks = [t for t in tasks if t['id'] != task_id]
        if len(tasks) == before:
            return  # mirror old behavior: silent no-op when id missing
        self._write(tasks)
        self._commit_and_push(f"rm: {task_id}")

    def move_task(self, task_id, new_date):
        self._mutate(task_id, {'due_date': _iso(new_date)},
                     f"move: {task_id} -> {_iso(new_date)}")

    def rename_task(self, task_id, new_description):
        self._ensure_synced(force_pull=True)
        tasks = self._read()
        for t in tasks:
            if t['id'] == task_id:
                t['description'] = new_description
                self._write(tasks)
                self._commit_and_push(f"rename: {task_id} -> {new_description}")
                return
        raise ValueError(f"Task {task_id} not found.")

    def push_tasks(self, from_date=None, to_date=None):
        self._ensure_synced(force_pull=True)
        from_iso = _iso(from_date or date.today())
        to_iso = _iso(to_date or (date.today() + timedelta(days=1)))
        tasks = self._read()
        moved = 0
        for t in tasks:
            if t.get('status') == 'pending' and t['due_date'] <= from_iso:
                t['due_date'] = to_iso
                moved += 1
        if moved:
            self._write(tasks)
            self._commit_and_push(f"push: {moved} task(s) -> {to_iso}")
        return moved

    def _mutate(self, task_id, fields, message):
        self._ensure_synced(force_pull=True)
        tasks = self._read()
        hit = False
        for t in tasks:
            if t['id'] == task_id:
                t.update(fields)
                hit = True
                break
        if not hit:
            return
        self._write(tasks)
        self._commit_and_push(message)

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
