"""Shared test scaffolding. Four suites had verbatim copies of the git
fixture setup and three had copies of the tasks.jsonl reader; a fix to one
never reached the others."""

import json
import os
import subprocess


def git(args, cwd, check=True):
    return subprocess.run(['git'] + args, cwd=cwd, capture_output=True,
                          text=True, check=check)


def set_identity(path):
    git(['config', 'user.email', 'test@example.com'], cwd=path)
    git(['config', 'user.name', 'Test'], cwd=path)


def setup_repo(path):
    """An empty git repo with a configured identity."""
    git(['init', '-q', '-b', 'main'], cwd=path)
    set_identity(path)


def parse_tasks(text):
    """Task objects from tasks.jsonl content: skip blanks, keep lines with an id."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if 'id' in obj:
            out.append(obj)
    return out


def read_tasks(repo_path):
    with open(os.path.join(repo_path, 'tasks.jsonl')) as f:
        return parse_tasks(f.read())
