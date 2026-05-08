"""Thin subprocess wrappers around the git operations lazy needs.

Every function returns (ok: bool, stderr: str). Nothing raises; the store
decides what to do on failure (warn, retry, abort).
"""

import os
import subprocess

_TIMEOUT = 30


def _run(args, cwd):
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=_TIMEOUT
        )
        return result.returncode == 0, (result.stderr or '').strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, str(e)


def is_repo(path):
    if not os.path.isdir(path):
        return False
    ok, _ = _run(['git', 'rev-parse', '--git-dir'], cwd=path)
    return ok


def has_remote(path):
    ok, out = _run(['git', 'config', '--get', 'remote.origin.url'], cwd=path)
    return ok and out != ''


def init_repo(path):
    """Initialize a fresh repo at path. Used for tests; real installs clone."""
    os.makedirs(path, exist_ok=True)
    return _run(['git', 'init', '-q', '-b', 'main'], cwd=path)


def clone(url, dest):
    parent = os.path.dirname(os.path.abspath(dest)) or '.'
    os.makedirs(parent, exist_ok=True)
    return _run(['git', 'clone', '-q', url, dest], cwd=parent)


def pull_ff(path):
    return _run(['git', 'pull', '--ff-only', '-q'], cwd=path)


def pull_rebase(path):
    return _run(['git', 'pull', '--rebase', '-q'], cwd=path)


def add_and_commit(path, filename, message):
    ok, err = _run(['git', 'add', filename], cwd=path)
    if not ok:
        return ok, err
    # Empty diff = nothing to commit; treat as success.
    clean, _ = _run(['git', 'diff', '--cached', '--quiet'], cwd=path)
    if clean:
        return True, ''
    return _run(['git', 'commit', '-q', '-m', message], cwd=path)


def push(path):
    return _run(['git', 'push', '-q'], cwd=path)
