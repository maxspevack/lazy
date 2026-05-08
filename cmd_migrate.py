"""lazy migrate-from-sqlite — one-shot migration from old SQLite to gist."""

import os
import sqlite3
import sys

from store import open_store, StoreNotInitialized, _utcnow


def cmd_migrate(args):
    db_path = args.db_path
    if db_path is None:
        base = os.path.dirname(os.path.abspath(sys.argv[0]))
        db_path = os.path.join(base, 'lazy.db')
    db_path = os.path.expanduser(db_path)

    if not os.path.exists(db_path):
        print(f"No SQLite DB found at {db_path}.", file=sys.stderr)
        sys.exit(1)

    try:
        store = open_store()
    except StoreNotInitialized as e:
        print(e, file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    conn.close()

    if not rows:
        print(f"No rows to migrate in {db_path}.")
        return

    existing = store._read()
    existing_ids = {t['id'] for t in existing}

    new_tasks = list(existing)
    skipped = 0
    for row in rows:
        if row['id'] in existing_ids:
            skipped += 1
            continue
        new_tasks.append({
            'id': row['id'],
            'description': row['description'],
            'due_date': row['due_date'],
            'status': row['status'],
            'created_at': row['created_at'] or _utcnow(),
        })

    migrated = len(rows) - skipped
    if migrated == 0:
        print("Nothing new to migrate (all ids already present).")
        return

    store._write(new_tasks)
    store._commit_and_push(f"migrate: {migrated} task(s) from sqlite")

    backup = db_path + '.migrated'
    os.rename(db_path, backup)

    print(f"Migrated {migrated} task(s). Source renamed to {backup}.")
    if skipped:
        print(f"Skipped {skipped} (id already present).")
