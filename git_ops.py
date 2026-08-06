"""Thin subprocess wrappers around the git operations lazy needs.

Every function returns (ok: bool, stderr: str). Nothing raises; the store
decides what to do on failure (warn, retry, abort).
"""

import os
import subprocess

_TIMEOUT = 30        # network operations
_LOCAL_TIMEOUT = 5   # plumbing that never touches the remote


_LOCAL_CMDS = {'rev-parse', 'status', 'diff', 'config', 'rev-list', 'init', 'add'}


def _run(args, cwd):
    """Returns (ok, output). Output is stdout on success, stderr on failure."""
    timeout = _LOCAL_TIMEOUT if len(args) > 1 and args[1] in _LOCAL_CMDS else _TIMEOUT
    # capture_output covers stdout/stderr but NOT stdin: a git credential
    # prompt would otherwise read from the MCP server's JSON-RPC channel,
    # eating client requests. Fail the prompt instead of answering it.
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_ASKPASS='', SSH_ASKPASS='')
    try:
        result = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            stdin=subprocess.DEVNULL, env=env
        )
        ok = result.returncode == 0
        out = (result.stdout if ok else result.stderr) or ''
        return ok, out.strip()
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


def unpushed_count(path):
    """Count of local commits ahead of upstream. Zero on any error."""
    ok, out = _run(['git', 'rev-list', '--count', '@{u}..HEAD'], cwd=path)
    if not ok:
        return 0
    try:
        return int(out)
    except ValueError:
        return 0


def is_dirty(path):
    """True if the working tree or index has uncommitted changes."""
    ok, out = _run(['git', 'status', '--porcelain'], cwd=path)
    return ok and out != ''


def rebase_in_progress(path):
    """True if a rebase is stopped mid-flight. HEAD is detached in that state,
    so any commit we make would land somewhere the branch cannot reach."""
    ok, gitdir = _run(['git', 'rev-parse', '--absolute-git-dir'], cwd=path)
    if not ok:
        return False
    return any(os.path.exists(os.path.join(gitdir, d))
               for d in ('rebase-merge', 'rebase-apply'))


def rebase_abort(path):
    """Return to the pre-rebase state. Local commits are preserved."""
    return _run(['git', 'rebase', '--abort'], cwd=path)
