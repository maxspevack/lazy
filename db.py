import sqlite3
import os
import functools
from datetime import date, datetime, timedelta

DB_NAME = 'lazy.db'

def get_db_path():
    """Returns the absolute path to the sqlite database file."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, 'lazy.db')

def get_connection():
    """Creates and returns a new SQLite connection with Row factory enabled."""
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema if it does not exist."""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            due_date DATE NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def with_connection(func):
    """
    Decorator to inject a database connection if one is not provided.
    If a connection is created by the decorator, it will be closed after the function executes.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        conn = kwargs.get('conn')
        should_close = False
        
        if conn is None:
            conn = get_connection()
            should_close = True
            kwargs['conn'] = conn
            
        try:
            return func(*args, **kwargs)
        finally:
            if should_close:
                conn.close()
    return wrapper

@with_connection
def add_task(description, due_date, conn=None):
    """Adds a new task to the database."""
    c = conn.cursor()
    c.execute('INSERT INTO tasks (description, due_date) VALUES (?, ?)', (description, due_date))
    new_id = c.lastrowid
    conn.commit()
    return new_id

@with_connection
def get_tasks(mode='today', conn=None):
    """
    Retrieves tasks based on the specified mode.
    mode: 'today' (includes overdue) or 'all'.
    """
    c = conn.cursor()
    today_str = date.today().isoformat()
    
    if mode == 'today':
        c.execute('''
            SELECT * FROM tasks 
            WHERE status = 'pending' AND due_date <= ? 
            ORDER BY due_date ASC, id ASC
        ''', (today_str,))
    elif mode == 'all':
        c.execute('''
            SELECT * FROM tasks 
            WHERE status = 'pending' 
            ORDER BY due_date ASC, id ASC
        ''')
    
    return c.fetchall()

@with_connection
def get_task(task_id, conn=None):
    """Retrieves a single task by ID."""
    c = conn.cursor()
    c.execute('SELECT * FROM tasks WHERE id = ?', (task_id,))
    return c.fetchone()

@with_connection
def complete_task(task_id, conn=None):
    """Marks a task as 'done'."""
    c = conn.cursor()
    c.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
    conn.commit()

@with_connection
def delete_task(task_id, conn=None):
    """Permanently deletes a task."""
    c = conn.cursor()
    c.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()

@with_connection
def move_task(task_id, new_date, conn=None):
    """Updates the due date of a task."""
    c = conn.cursor()
    c.execute("UPDATE tasks SET due_date = ? WHERE id = ?", (new_date, task_id))
    conn.commit()

@with_connection
def push_tasks(from_date=None, to_date=None, conn=None):
    """
    Moves all pending tasks due on or before `from_date` to `to_date`.
    Returns the number of tasks updated.
    """
    if from_date is None:
        from_date = date.today()
    if to_date is None:
        to_date = date.today() + timedelta(days=1)
        
    c = conn.cursor()
    c.execute("UPDATE tasks SET due_date = ? WHERE status = 'pending' AND due_date <= ?", (to_date, from_date))
    count = c.rowcount
    conn.commit()
    return count
