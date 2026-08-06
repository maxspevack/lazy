#!/usr/bin/env python3
"""MCP server: JSON-RPC over stdio. Wraps the Store for AI clients."""

import json
import os
import random
import re
import sys

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(base_dir)

from store import open_store, StoreNotInitialized
from utils import parse_date, load_config


def _schema(properties=None, required=None):
    s = {"type": "object", "properties": properties or {}}
    if required:
        s["required"] = required
    return s


_DESC = {"type": "string"}
_INT = {"type": "integer"}
_DATE = {"type": "string", "description": "Natural language date supported"}

TOOLS = [
    {"name": "lazy_add", "description": "Add a new task. Use natural language for dates (e.g., 'tmw', 'next fri', 'soon').",
     "inputSchema": _schema({"description": _DESC, "due_date": _DATE}, ["description"])},
    {"name": "lazy_list", "description": "List pending tasks. Defaults to today's and overdue.",
     "inputSchema": _schema({"mode": {"type": "string", "enum": ["today", "all"]}})},
    {"name": "lazy_done", "description": "Mark a task complete by ID.",
     "inputSchema": _schema({"id": _INT}, ["id"])},
    {"name": "lazy_rename", "description": "Rename a task's description by ID.",
     "inputSchema": _schema({"id": _INT, "description": _DESC}, ["id", "description"])},
    {"name": "lazy_move", "description": "Reschedule a task to a new date.",
     "inputSchema": _schema({"id": _INT, "due_date": _DATE}, ["id", "due_date"])},
    {"name": "lazy_push", "description": "The 'Panic Button'. Pushes all today's tasks to tomorrow.",
     "inputSchema": _schema()},
    {"name": "lazy_get_messages", "description": "Inspect the LulzCorp message catalog.",
     "inputSchema": _schema({"category": {"type": "string", "enum": ["completion", "empty"]}}, ["category"])},
]


def _h_add(store, a, cfg):
    d = parse_date(a.get("due_date", "today"))
    new_id = store.add_task(a["description"], d)
    return f"Added task [{new_id}] '{a['description']}' for {d}."


def _h_list(store, a, cfg):
    tasks = store.get_tasks(a.get("mode", "today"))
    if not tasks:
        return f"✨ {random.choice(cfg.get('empty_state_messages', ['Nothing to do!']))}"
    rows = [f"{t['id']:<3} | {t.get('due_date', '?')} | {_clean(t['description'])}"
            for t in tasks]
    return "ID | Due Date | Description\n" + "-" * 30 + "\n" + "\n".join(rows) + "\n"


_CTRL_RE = re.compile(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]')


def _clean(text):
    """Strip C0/C1 control characters. Descriptions round-trip through a
    network-synced gist into both a terminal and the model's context; escape
    sequences have no business in either."""
    return _CTRL_RE.sub('', str(text))


def _coerce_id(a):
    """Accept an id the client stringified. Without this, {"id": "1"} produced
    a confident 'not found' for a task that exists."""
    if "id" in a:
        a = dict(a, id=int(a["id"]))
    return a


def _h_done(store, a, cfg):
    a = _coerce_id(a)
    t = store.get_task(a["id"])
    if not t:
        return f"Task [{a['id']}] not found."
    store.complete_task(a["id"])
    praise = random.choice(cfg.get('completion_messages', ["Done."]))
    return f"Task [{a['id']}] '{t['description']}' marked as done.\n\n✨ {praise}"


def _h_rename(store, a, cfg):
    a = _coerce_id(a)
    t = store.get_task(a["id"])
    if not t:
        return f"Task [{a['id']}] not found."
    store.rename_task(a["id"], a["description"])
    return f"Task [{a['id']}] renamed to '{a['description']}'."


def _h_move(store, a, cfg):
    a = _coerce_id(a)
    t = store.get_task(a["id"])
    if not t:
        return f"Task [{a['id']}] not found."
    new_date = parse_date(a.get("due_date", "today"))
    store.move_task(a["id"], new_date)
    return f"Task [{a['id']}] '{t['description']}' moved to {new_date}."


def _h_push(store, a, cfg):
    return f"Pushed {store.push_tasks()} tasks to tomorrow. Rest easy."


def _h_get_messages(store, a, cfg):
    key = 'completion_messages' if a.get("category") == 'completion' else 'empty_state_messages'
    msgs = "\n".join(f"- {m}" for m in cfg.get(key, []))
    return f"LulzCorp Brand Messages ({a.get('category')}):\n\n{msgs}"


HANDLERS = {
    "lazy_add": _h_add, "lazy_list": _h_list, "lazy_done": _h_done,
    "lazy_rename": _h_rename, "lazy_move": _h_move, "lazy_push": _h_push,
    "lazy_get_messages": _h_get_messages,
}
NEEDS_STORE = {"lazy_get_messages": False}  # default True; only this is False


def _handle_call(params):
    name = params.get("name")
    args = params.get("arguments", {})
    cfg = load_config()
    handler = HANDLERS.get(name)
    if handler is None:
        return {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {name}"}]}
    store = None
    if NEEDS_STORE.get(name, True):
        try:
            store = open_store()
        except StoreNotInitialized as e:
            return {"isError": True, "content": [{"type": "text", "text": str(e)}]}
    try:
        text = handler(store, args, cfg)
    except Exception as e:
        # Tool-level error, not a protocol error: the request stays answerable,
        # so the client never waits on a response that will not come.
        return {"isError": True,
                "content": [{"type": "text",
                             "text": f"{name} failed: {type(e).__name__}: {e}"}]}
    return {"content": [{"type": "text", "text": text}]}


def _handle(method, params):
    if method == "initialize":
        return {"protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"list": True}},
                "serverInfo": {"name": "lazy-mcp", "version": "1.0.0"}}, None
    if method == "tools/list":
        return {"tools": TOOLS}, None
    if method == "tools/call":
        return _handle_call(params), None
    return None, {"code": -32601, "message": f"Method not found: {method}"}


def main():
    while True:
        req_id = None
        try:
            line = sys.stdin.readline()
            if not line:
                break
            req = json.loads(line)
            req_id = req.get("id")
            if req_id is None:
                continue  # notifications get no response
            result, err = _handle(req.get("method"), req.get("params", {}))
            resp = {"jsonrpc": "2.0", "id": req_id}
            if result is not None:
                resp["result"] = result
            elif err is not None:
                resp["error"] = err
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            # id is null only when it could not be read (parse error); an
            # id-less error frame is unmatchable, and strict clients drop it
            # and wait forever on the original request.
            sys.stdout.write(json.dumps(
                {"jsonrpc": "2.0", "id": req_id,
                 "error": {"code": -32603, "message": str(e)}}
            ) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
