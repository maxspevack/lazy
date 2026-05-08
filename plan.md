# Plan: Lazy as a Local Clone of a Private Gist (JSONL)

**Status:** Draft, awaiting review
**Author:** Max Spevack (with Claude)
**Date:** 2026-05-08
**Supersedes:** Previous draft of this file (Sheets-as-backend design)

---

## 1. Goal

Make `lazy` work seamlessly across multiple machines (Spark, Fedora, MacBook,
narf-triage) by storing tasks in a private GitHub Gist, treated as a local
git clone with offline-tolerant push/pull. SQLite goes away entirely.

## 2. Non-goals

- **Multi-user collaboration.** A gist can be shared, but lazy is single-user.
- **Real-time push.** No daemons, no webhooks, no watchers. Sync happens
  on-demand at command boundaries.
- **Schema migrations.** v1 schema is frozen. If we need to add fields later,
  we'll write a migration script then.
- **Encryption at rest.** Gist is private (visible only to authenticated
  owner). That's the trust boundary.

## 3. Mental model

> The gist is the *canonical* state.
> The local clone is the *working* copy.
> Lazy is a thin CLI that mutates the working copy and lets git handle sync.

```
                    ┌──────────────────────────────┐
                    │  Private Gist (gist.github)  │
                    │       tasks.jsonl            │
                    └──────────────┬───────────────┘
                                   │  git
                ┌──────────────────┼──────────────────┐
                ▼                  ▼                  ▼
       ~/.local/share/      ~/.local/share/    ~/.local/share/
        lazy/repo/           lazy/repo/         lazy/repo/
        Spark                Fedora             MacBook
        (working copy)       (working copy)     (working copy)
```

Every machine's working copy is a real git checkout. Lazy commands run
locally against the JSONL file. Reads pull (with a freshness window).
Writes commit + push (sync by default; offline mode for planes).

## 4. Data layout

```
~/.config/lazy/
└── config.json                # Gist ID, clone path, options

~/.local/share/lazy/
├── repo/                      # git clone of the private gist
│   └── tasks.jsonl            # the task list
└── .last-pull                 # mtime sentinel for freshness window
```

`config.json`:

```json
{
  "gist_id": "abc123def456",
  "repo_path": "~/.local/share/lazy/repo",
  "pull_freshness_seconds": 30,
  "auto_push": true,
  "enable_colors": true,
  "completion_messages": [...],
  "empty_state_messages": [...],
  "add_echo_messages": [...]
}
```

(Existing `enable_colors`, `completion_messages`, etc. stay — they're vibe
data, not storage data.)

## 5. Storage format

`tasks.jsonl` — one JSON object per line, no array wrapping:

```jsonl
{"id":1,"description":"buy milk","due_date":"2026-05-09","status":"pending","created_at":"2026-05-08T14:23:01Z"}
{"id":2,"description":"call dad","due_date":"2026-05-12","status":"pending","created_at":"2026-05-08T15:01:33Z"}
{"id":3,"description":"ship narf release","due_date":"2026-05-07","status":"done","created_at":"2026-05-06T09:11:00Z"}
```

Schema (frozen for v1):

| Field | Type | Notes |
|---|---|---|
| `id` | int | Monotonic, machine-local `max+1` allocation |
| `description` | string | Free text |
| `due_date` | string | ISO 8601 date (`YYYY-MM-DD`) |
| `status` | string | `pending` or `done` |
| `created_at` | string | ISO 8601 timestamp with `Z` suffix |

Lines are sorted by `id` ascending on every write (deterministic file order
keeps git diffs minimal — same task always lives on the same line until its
content changes).

**Why JSONL, not JSON / TOML / YAML / Markdown:**
- One task per line = git diff per task. Adding a task is a one-line diff.
- Two machines adding tasks = two new lines, no merge conflict.
- Strict schema (every line is a JSON object) — beats markdown's autocorrect
  vulnerability on phones.
- Trivial to parse with stdlib `json` module. No new deps.
- `cat tasks.jsonl | jq -s` for ad-hoc queries.

## 6. Sync model

### 6.1 Read path

```
1. If now() - last_pull > pull_freshness_seconds:
       run `git -C repo pull --ff-only`
       update .last-pull mtime
   (if pull fails: log warning to stderr, continue with stale local copy)
2. Read tasks.jsonl line by line, parse each as JSON
3. Filter / sort in memory per command's needs
```

The freshness window keeps interactive sessions snappy. `lazy list` followed
by `lazy done 14` two seconds later doesn't pull twice.

### 6.2 Write path

```
1. Pull (always, regardless of freshness — we want the latest before mutating)
2. Read tasks.jsonl
3. Mutate in memory (add/done/move/rename/delete/push)
4. Write atomic: tmp file → rename
5. git add tasks.jsonl && git commit -m "<action>: <summary>"
6. If auto_push:
       git push
   On push reject (remote moved):
       git pull --rebase
       (if rebase clean) git push
       (else) tell the user about the conflict, exit non-zero
   On network failure:
       leave commit local, warn user, exit 0
       (next successful sync flushes the queue)
```

### 6.3 Conflict resolution

For pure additions on different machines: lines have different IDs and live
on different lines. `git pull` merges trivially. No conflict.

For edits on the same task from two machines: same line modified two ways.
Git surfaces a real merge conflict. Lazy detects this and prints:

```
lazy: sync conflict on task 14. Resolve in ~/.local/share/lazy/repo/tasks.jsonl
      and run `lazy resolve` when done.
```

`lazy resolve` runs `git add tasks.jsonl && git rebase --continue && git push`.
For a single user with rare cross-machine same-task edits, this should fire
maybe once a year.

### 6.4 Offline mode

Set `auto_push: false` in config, OR pass `--no-sync` to a single command,
OR simply have no network. Lazy still works:

- Reads use the local clone.
- Writes commit locally without pushing.
- Subsequent online use auto-pushes the queue.

The plane case works. The "I lost my laptop with unpushed commits" case
loses those commits — we accept that for v1; addressing it would require
real persistence outside the local clone, which is a different product.

### 6.5 ID allocation race

Two machines both run `lazy add` while offline, both pick `id = 14`. When
both come online and try to push, the second one rebases. After rebase, the
file has two tasks with `id=14`. Lazy detects duplicates on read and prints:

```
lazy: duplicate id 14 detected. Renumbering oldest task to 15.
```

…and rewrites the file. Loss-free, deterministic, surfaced clearly. With
`auto_push=true` and pull-before-write, this should fire essentially never.

## 7. Bootstrap (`lazy init`)

```
$ lazy init
Checking gh authentication... ok (logged in as maxspevack)
Creating private gist 'lazy-tasks'... ok (id: abc123def456)
Cloning to ~/.local/share/lazy/repo... ok
Writing initial tasks.jsonl... ok
Committing and pushing... ok

Lazy is ready. On other machines, run:
  lazy init --from-gist abc123def456
```

`lazy init --from-gist <id>` clones an existing gist to the local path.
Used on machines 2 and 3.

`lazy init --check` validates everything (gh authed, repo cloned, push
permissions, schema valid).

## 8. Code changes

### 8.1 Files removed

- `db.py` — SQLite logic. Gone.
- `lazy.db` — the database file. Gone (after one-time migration).

### 8.2 Files added

- `store.py` — the new storage module. Functions:
  - `init_store(gist_id_or_create)` — bootstrap
  - `read_tasks() -> list[dict]` — pull (if stale) + parse
  - `write_tasks(tasks: list[dict], commit_msg: str)` — atomic write + commit + push
  - `next_id(tasks) -> int` — `max(t.id) + 1`
  - `resolve_conflict()` — for `lazy resolve`
- `git_ops.py` — thin subprocess wrappers around `git pull --ff-only`,
  `git commit`, `git push`, `git pull --rebase`. Each returns `(ok, stderr)`.

### 8.3 Files modified

- `lazy` — replace `from db import (...)` with `from store import read_tasks, write_tasks, next_id`. Each command becomes:
  ```python
  tasks = read_tasks()
  # mutate
  write_tasks(tasks, commit_msg=f"add: {description}")
  ```
  All 8 current `db.py` operations collapse into "read list, mutate list,
  write list."
- `mcp_server.py` — same transformation.
- `config.json` — add `gist_id`, `repo_path`, `pull_freshness_seconds`,
  `auto_push` keys.
- `pyproject.toml` — remove any sqlite-related extras (none currently).
  Add no new deps; we use `subprocess` to call `git`/`gh`.
- `README.md` — bootstrap walkthrough, offline-mode note.
- `RELEASE_NOTES.md` — major version bump (storage format change is
  breaking).

### 8.4 New CLI subcommands

```
lazy init [--from-gist <id>]   Bootstrap (one-time per machine)
lazy init --check              Validate setup
lazy resolve                   After a sync conflict, mark resolved and push
lazy sync                      Force pull + push (for "I'm back online")
lazy backend                   Print gist URL, local clone path, last sync time
```

## 9. Migration from existing SQLite

```
lazy migrate-from-sqlite [--db <path>]
```

One-shot tool:
1. Read all rows from `lazy.db` (or `LAZY_DB_PATH`).
2. Initialize a new private gist if not already configured.
3. Write each row as a JSONL line, preserving IDs.
4. Commit + push.
5. Rename `lazy.db` to `lazy.db.migrated` (don't delete — paranoia tax is
   one filename character).

Run on whichever machine has the canonical SQLite file. Other machines
`lazy init --from-gist <id>` after.

## 10. Failure modes

| Failure | Behavior |
|---|---|
| `gh` not installed | `lazy init` fails with install instructions; existing installs unaffected |
| `gh` not authenticated | `lazy init` fails with `gh auth login` instruction |
| Network down on read | Use stale local clone, warn once on stderr |
| Network down on write | Commit locally, warn once on stderr, exit 0 |
| Push rejected (remote moved) | Auto pull-rebase + retry. Surfaces only if rebase has true conflict. |
| Same-task edit conflict | Print clear instruction to use `lazy resolve` |
| Duplicate ID after merge | Auto-renumber oldest, print warning |
| Corrupted JSONL line | Skip line, warn on stderr (don't crash the list) |
| Local repo missing | `lazy init --from-gist <configured-id>` re-clones |

## 11. Phased plan

### Phase 1 — Storage rewrite
- [ ] Implement `store.py` and `git_ops.py`
- [ ] Replace `db.py` callsites in `lazy` and `mcp_server.py`
- [ ] Hand-test against a local clone of a personal gist
- [ ] Existing tests rewritten to point at a temp clone (no remote)
- **Verify:** all CLI commands work end-to-end against a real gist on one
  machine

### Phase 2 — Multi-machine validation
- [ ] `lazy init --from-gist` on a second machine
- [ ] Cross-machine smoke test: add on Fedora, list on Spark, done on
  MacBook, verify state converges
- **Verify:** every machine sees consistent state after each operation

### Phase 3 — Failure-mode coverage
- [ ] Test offline write (disable network, run `lazy add`, re-enable, run
  `lazy sync`)
- [ ] Test concurrent-add race (offline both machines, add tasks on each,
  bring both online, verify renumbering)
- [ ] Test same-task edit conflict (rename same task on two machines,
  verify `lazy resolve` flow)
- **Verify:** documented behaviors in §10 actually happen

### Phase 4 — Migration + docs + release
- [ ] `lazy migrate-from-sqlite` implementation
- [ ] README rewritten with bootstrap walkthrough
- [ ] RELEASE_NOTES with breaking-change notice
- [ ] Tag release

## 12. Tradeoffs (honest)

**What this gets:**
- Multi-machine sync via the most boring, well-understood tool on Earth (git).
- Offline capable. Lazy works on a plane.
- No new SaaS dependency beyond GitHub, which you already trust.
- No new auth flow — `gh` is already authed everywhere.
- Free audit log — `git -C ~/.local/share/lazy/repo log` shows every task
  you've ever added or touched.
- Phone access to the data via the GitHub mobile app or web UI on the gist.
- Lazy becomes a pure-Python tool with no native dependencies (sqlite3 was
  technically a stdlib dep, but the C extension is now gone from the runtime
  surface).
- The data file is human-readable and human-editable. `vim
  ~/.local/share/lazy/repo/tasks.jsonl` works.

**What this costs:**
- A few hundred ms of latency on every command for the `git pull` /
  `git push` round-trips. The freshness window mitigates reads; writes
  always pay it.
- A real `lazy init` flow new users have to do once. Documented but
  non-zero.
- Public-tool dependency on `gh` (or at least on `git` + a GitHub auth
  setup). Reasonable for the audience but worth flagging.
- Edit conflicts are now possible (very rare, but real). The previous
  SQLite-on-one-machine design had zero conflict surface.
- The breaking storage format change requires a one-time migration for
  existing users (i.e., you).

## 13. Open questions

1. **Gist or private repo?** A regular private repo on GitHub gives you
   GitHub's full UI (issues, releases, branch protection — none of which
   you need). A gist is one-file, lighter, has its own URL space, and
   matches the "small artifact" feel of lazy. *Recommendation: gist.*

2. **Sync push or async push?** Sync (default `auto_push=true`) costs
   ~500ms per write but guarantees the gist matches local. Async would
   require a background process / atexit hook and risks losing commits on
   process kill. *Recommendation: sync.*

3. **Where do `last-pull` mtimes live?** A sidecar file, a git-config
   value, or a stat on `tasks.jsonl`? *Recommendation: sidecar `.last-pull`
   in the lazy local-data dir, separate from the repo.*

4. **Should `lazy` also expose `--gist-id <id>` per-command override?**
   Lets one user run multiple lazy lists (work vs personal). Modest
   feature, deferrable. *Recommendation: defer to v2.*

5. **HTTPS-via-gh-credential-helper or SSH for git remote?** SSH requires
   a key on each machine; HTTPS via `gh auth setup-git` is the path of
   least resistance. *Recommendation: HTTPS via gh credential helper.*

6. **What does `lazy backend` show?** *Recommendation:*
   ```
   gist:        abc123def456 (https://gist.github.com/maxspevack/abc123)
   local clone: ~/.local/share/lazy/repo (clean, pushed)
   last pull:   2026-05-08 14:32:01 (12s ago)
   tasks:       13 pending, 47 done
   ```

7. **Do we keep a separate `done_archive.jsonl`?** Live list keeps growing
   if we never archive. *Recommendation: defer. With <500 tasks lifetime,
   no problem. Add `lazy archive` subcommand later if it becomes one.*

## 14. Decision points for review

Mark each ✅ accept, ❌ reject, or annotate:

- [ ] JSONL as the storage format (vs JSON, TOML, markdown)
- [ ] Gist (vs private repo) as the sync target
- [ ] `~/.local/share/lazy/repo/` as the clone location
- [ ] `~/.config/lazy/config.json` as the new config location
- [ ] Sync push by default with `--no-sync` opt-out
- [ ] 30-second pull freshness window default
- [ ] Auto-renumber on duplicate-ID detection (vs surface as conflict)
- [ ] `lazy migrate-from-sqlite` as the migration path
- [ ] Phased delivery as in §11
- [ ] Open questions 1–7 in §13 resolved per recommendation

When approved I'll start Phase 1.
