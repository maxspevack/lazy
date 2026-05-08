#!/usr/bin/env python3
import json
import sys
import os
import random

base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(base_dir)

from store import open_store, StoreNotInitialized
from utils import parse_date, load_config


def main():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line)
            method = request.get("method")
            req_id = request.get("id")

            # MCP specification: Notifications do not have an ID and MUST NOT be responded to.
            if req_id is None:
                continue

            response_result = None
            response_error = None

            if method == "initialize":
                response_result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"list": True}},
                    "serverInfo": {"name": "lazy-mcp", "version": "1.0.0"}
                }
            elif method == "tools/list":
                response_result = {
                    "tools": [
                        {
                            "name": "lazy_add",
                            "description": "Add a new task to the lazy todo list. Use natural language for dates (e.g., 'tmw', 'next fri', 'soon').",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "description": {"type": "string", "description": "The task description"},
                                    "due_date": {"type": "string", "description": "Optional due date (default: today)"}
                                },
                                "required": ["description"]
                            }
                        },
                        {
                            "name": "lazy_list",
                            "description": "List pending tasks. Defaults to today's and overdue tasks.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "mode": {"type": "string", "enum": ["today", "all"], "description": "Filter mode"}
                                }
                            }
                        },
                        {
                            "name": "lazy_done",
                            "description": "Mark a task as complete by its ID.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {"id": {"type": "integer", "description": "The task ID"}},
                                "required": ["id"]
                            }
                        },
                        {
                            "name": "lazy_rename",
                            "description": "Rename a task's description by its ID.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer", "description": "The task ID"},
                                    "description": {"type": "string", "description": "The new description"}
                                },
                                "required": ["id", "description"]
                            }
                        },
                        {
                            "name": "lazy_move",
                            "description": "Reschedule a task to a new date.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "integer", "description": "The task ID"},
                                    "due_date": {"type": "string", "description": "The new due date (natural language supported)"}
                                },
                                "required": ["id", "due_date"]
                            }
                        },
                        {
                            "name": "lazy_push",
                            "description": "The 'Panic Button'. Pushes all today's tasks to tomorrow.",
                            "inputSchema": {"type": "object", "properties": {}}
                        },
                        {
                            "name": "lazy_get_messages",
                            "description": "Retrieve the list of completion and empty-state messages from the LulzCorp brand config.",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "category": {"type": "string", "enum": ["completion", "empty"], "description": "Message category"}
                                },
                                "required": ["category"]
                            }
                        }
                    ]
                }
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                result = {"content": []}
                config = load_config()

                # lazy_get_messages doesn't need the store
                if tool_name == "lazy_get_messages":
                    category = arguments.get("category")
                    key = 'completion_messages' if category == 'completion' else 'empty_state_messages'
                    messages = config.get(key, [])
                    output = "\n".join([f"- {m}" for m in messages])
                    result["content"].append({"type": "text", "text": f"LulzCorp Brand Messages ({category}):\n\n{output}"})
                    response_result = result
                else:
                    try:
                        store = open_store()
                    except StoreNotInitialized as e:
                        result = {"isError": True, "content": [{"type": "text", "text": str(e)}]}
                        response_result = result
                        # send response and continue loop
                        response = {"jsonrpc": "2.0", "id": req_id, "result": response_result}
                        sys.stdout.write(json.dumps(response) + "\n")
                        sys.stdout.flush()
                        continue

                    if tool_name == "lazy_add":
                        desc = arguments.get("description")
                        d_str = arguments.get("due_date", "today")
                        d_date = parse_date(d_str)
                        new_id = store.add_task(desc, d_date)
                        result["content"].append({"type": "text", "text": f"Added task [{new_id}] '{desc}' for {d_date}."})

                    elif tool_name == "lazy_list":
                        mode = arguments.get("mode", "today")
                        tasks = store.get_tasks(mode)
                        if not tasks:
                            messages = config.get('empty_state_messages', ["Nothing to do!"])
                            result["content"].append({"type": "text", "text": f"✨ {random.choice(messages)}"})
                        else:
                            output = "ID | Due Date | Description\n" + "-" * 30 + "\n"
                            for t in tasks:
                                output += f"{t['id']:<3} | {t['due_date']} | {t['description']}\n"
                            result["content"].append({"type": "text", "text": output})

                    elif tool_name == "lazy_done":
                        t_id = arguments.get("id")
                        task = store.get_task(t_id)
                        if task:
                            store.complete_task(t_id)
                            praises = config.get('completion_messages', ["Done."])
                            praise = random.choice(praises)
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] '{task['description']}' marked as done.\n\n✨ {praise}"})
                        else:
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] not found."})

                    elif tool_name == "lazy_push":
                        count = store.push_tasks()
                        result["content"].append({"type": "text", "text": f"Pushed {count} tasks to tomorrow. Rest easy."})

                    elif tool_name == "lazy_rename":
                        t_id = arguments.get("id")
                        new_desc = arguments.get("description")
                        task = store.get_task(t_id)
                        if task:
                            store.rename_task(t_id, new_desc)
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] renamed to '{new_desc}'."})
                        else:
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] not found."})

                    elif tool_name == "lazy_move":
                        t_id = arguments.get("id")
                        d_str = arguments.get("due_date", "today")
                        task = store.get_task(t_id)
                        if task:
                            new_date = parse_date(d_str)
                            store.move_task(t_id, new_date)
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] '{task['description']}' moved to {new_date}."})
                        else:
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] not found."})

                    else:
                        result = {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}
                    response_result = result
            else:
                response_error = {"code": -32601, "message": f"Method not found: {method}"}

            response = {"jsonrpc": "2.0", "id": req_id}
            if response_result is not None:
                response["result"] = response_result
            elif response_error is not None:
                response["error"] = response_error

            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()

        except Exception as e:
            err_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(err_response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
