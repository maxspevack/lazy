"""lazy init — bootstrap a gist-backed clone."""

import json
import os
import subprocess
import sys
import tempfile

import git_ops
from store import DEFAULT_REPO

CONFIG_DIR = os.path.expanduser('~/.config/lazy')
CONFIG_PATH = os.path.join(CONFIG_DIR, 'config.json')


def _check_gh():
    try:
        result = subprocess.run(
            ['gh', 'auth', 'status'], capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _read_config():
    try:
        with open(CONFIG_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _write_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    # The gist URL is the entire access control surface for a secret gist.
    # Anyone reading this file gets full read access to your tasks. Lock it
    # to owner-only.
    with open(CONFIG_PATH, 'w') as f:
        json.dump(cfg, f, indent=2)
        f.write('\n')
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass


def _create_gist(description="lazy task list"):
    """Create a private gist with a placeholder tasks.jsonl. Return (gist_id, url)."""
    with tempfile.TemporaryDirectory() as td:
        seed = os.path.join(td, 'tasks.jsonl')
        with open(seed, 'w') as f:
            f.write('{"_init": true}\n')
        result = subprocess.run(
            ['gh', 'gist', 'create',
             '--filename', 'tasks.jsonl',
             '--desc', description,
             seed],
            capture_output=True, text=True, timeout=30
        )
    if result.returncode != 0:
        print(f"gh gist create failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    url = result.stdout.strip().splitlines()[-1]
    gist_id = url.rstrip('/').split('/')[-1]
    return gist_id, url


def _clone(gist_id, dest):
    url = f"https://gist.github.com/{gist_id}.git"
    return git_ops.clone(url, dest)


def cmd_init(args):
    cfg = _read_config()
    repo_path = os.path.expanduser(cfg.get('repo_path', DEFAULT_REPO))

    if os.path.exists(repo_path):
        print(f"Lazy is already initialized at {repo_path}.")
        print("  (Run `lazy backend` to inspect.)")
        return

    if not _check_gh():
        print("`gh` is not installed or not authenticated.", file=sys.stderr)
        print("Install gh and run `gh auth login`, then retry.", file=sys.stderr)
        sys.exit(1)

    gist_url = None
    if args.from_gist:
        gist_id = args.from_gist
        print(f"Cloning gist {gist_id} -> {repo_path}...")
    else:
        print("Creating new private gist...")
        gist_id, gist_url = _create_gist()
        print(f"  -> {gist_url}")
        print(f"Cloning -> {repo_path}...")

    ok, err = _clone(gist_id, repo_path)
    if not ok:
        print(f"Clone failed: {err}", file=sys.stderr)
        sys.exit(1)

    cfg['gist_id'] = gist_id
    cfg['repo_path'] = repo_path
    if gist_url:
        cfg['gist_url'] = gist_url
    _write_config(cfg)

    print(f"Lazy is ready. Config: {CONFIG_PATH}")
    if not args.from_gist:
        print(f"On other machines, run: lazy init --from-gist {gist_id}")


