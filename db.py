import sqlite3
import os
from datetime import date, timedelta

def get_db_path():
    """Path to the SQLite file. Overridable via LAZY_DB_PATH for tests."""
    override = os.environ.get('LAZY_DB_PATH')
    if override:
        return override
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'lazy.db')

def get_connection():
    """Open a SQLite connection with Row factory and ensure schema exists."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            due_date DATE NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    return conn

def _iso(d):
    return d.isoformat() if hasattr(d, 'isoformat') else d

def add_task(description, due_date, conn):
    c = conn.execute(
        'INSERT INTO tasks (description, due_date) VALUES (?, ?)',
        (description, _iso(due_date))
    )
    conn.commit()
    return c.lastrowid

def get_tasks(mode, conn):
    """Returns pending tasks. mode='today' filters to due <= today; mode='all' returns all pending."""
    if mode == 'today':
        return conn.execute(
            "SELECT * FROM tasks WHERE status='pending' AND due_date <= ? ORDER BY due_date, id",
            (date.today().isoformat(),)
        ).fetchall()
    return conn.execute(
        "SELECT * FROM tasks WHERE status='pending' ORDER BY due_date, id"
    ).fetchall()

def get_task(task_id, conn):
    return conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()

def complete_task(task_id, conn):
    conn.execute("UPDATE tasks SET status='done' WHERE id = ?", (task_id,))
    conn.commit()

def delete_task(task_id, conn):
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()

def move_task(task_id, new_date, conn):
    conn.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (_iso(new_date), task_id))
    conn.commit()

def rename_task(task_id, new_description, conn):
    c = conn.execute("UPDATE tasks SET description = ? WHERE id = ?", (new_description, task_id))
    if c.rowcount == 0:
        raise ValueError(f"Task {task_id} not found.")
    conn.commit()

def push_tasks(conn, from_date=None, to_date=None):
    """Move pending tasks due <= from_date to to_date. Returns count moved."""
    from_date = from_date or date.today()
    to_date = to_date or (date.today() + timedelta(days=1))
    c = conn.execute(
        "UPDATE tasks SET due_date = ? WHERE status='pending' AND due_date <= ?",
        (_iso(to_date), _iso(from_date))
    )
    conn.commit()
    return c.rowcount
