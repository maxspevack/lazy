#!/usr/bin/env python3
import json
import sys
import os
import random
from datetime import date

# Add the lazy directory to the path so we can import db and utils
base_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(base_dir)

from db import init_db, add_task, get_tasks, complete_task, delete_task, move_task, get_task, push_tasks, get_connection
from utils import parse_date, load_config

def main():
    # Initialize the database if it doesn't exist
    init_db()

    while True:
        try:
            # Read line from stdin
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

            # Simple stdio MCP protocol handling
            if method == "initialize":
                response_result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {
                            "list": True
                        }
                    },
                    "serverInfo": {
                        "name": "lazy-mcp",
                        "version": "1.0.0"
                    }
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
                                "properties": {
                                    "id": {"type": "integer", "description": "The task ID"}
                                },
                                "required": ["id"]
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
                
                conn = get_connection()
                try:
                    config = load_config()
                    if tool_name == "lazy_add":
                        desc = arguments.get("description")
                        d_str = arguments.get("due_date", "today")
                        d_date = parse_date(d_str)
                        new_id = add_task(desc, d_date, conn=conn)
                        result["content"].append({"type": "text", "text": f"Added task [{new_id}] '{desc}' for {d_date}."})
                    
                    elif tool_name == "lazy_list":
                        mode = arguments.get("mode", "today")
                        tasks = get_tasks(mode, conn=conn)
                        if not tasks:
                            messages = config.get('empty_state_messages', ["Nothing to do!"])
                            result["content"].append({"type": "text", "text": f"✨ {random.choice(messages)}"})
                        else:
                            output = "ID | Due Date | Description\n" + "-"*30 + "\n"
                            for t in tasks:
                                output += f"{t['id']:<3} | {t['due_date']} | {t['description']}\n"
                            result["content"].append({"type": "text", "text": output})
                    
                    elif tool_name == "lazy_done":
                        t_id = arguments.get("id")
                        task = get_task(t_id, conn=conn)
                        if task:
                            complete_task(t_id, conn=conn)
                            praises = config.get('completion_messages', ["Done."])
                            praise = random.choice(praises)
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] '{task['description']}' marked as done.\n\n✨ {praise}"})
                        else:
                            result["content"].append({"type": "text", "text": f"Task [{t_id}] not found."})
                    
                    elif tool_name == "lazy_push":
                        count = push_tasks(conn=conn)
                        result["content"].append({"type": "text", "text": f"Pushed {count} tasks to tomorrow. Rest easy."})
                    
                    elif tool_name == "lazy_get_messages":
                        category = arguments.get("category")
                        key = 'completion_messages' if category == 'completion' else 'empty_state_messages'
                        messages = config.get(key, [])
                        output = "\n".join([f"- {m}" for m in messages])
                        result["content"].append({"type": "text", "text": f"LulzCorp Brand Messages ({category}):\n\n{output}"})

                    else:
                        result = {"isError": True, "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}]}
                finally:
                    conn.close()
                response_result = result
            else:
                response_error = {"code": -32601, "message": f"Method not found: {method}"}
            
            # Send response if not a notification
            response = {"jsonrpc": "2.0", "id": req_id}
            if response_result is not None:
                response["result"] = response_result
            elif response_error is not None:
                response["error"] = response_error
            
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
            
        except Exception as e:
            # MCP errors should be returned as JSON-RPC error objects
            err_response = {
                "jsonrpc": "2.0",
                "id": None, # This is technically incorrect for a request, but safe for a crash
                "error": {"code": -32603, "message": str(e)}
            }
            sys.stdout.write(json.dumps(err_response) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
