# Lazy 🦥: The High-Frequency Altar of Procrastination

> "Why do today what you can push to tomorrow?"

`lazy` is not a task manager. It is a **Vibe Engineering** platform for the professional procrastinator. We recognize that guilt is a friction coefficient that we simply cannot afford. `lazy` allows you to aggressively defer, surgically ignore, and occasionally complete tasks with the detached grace of a hermit crab in vestments.

## 🤖 The Elite Interface: AI-First (MCP)

The truly high-status individual does not type commands. They delegate to the **Robot Workforce**. `lazy` is natively integrated with the **Model Context Protocol (MCP)**, allowing Gemini and other LulzCorp agents to manage your existential dread for you. This is the primary interface for the modern procrastinator.

### Tools for the Robot Workforce:
- **`lazy_add`**: Manifest a task from the void using natural language.
- **`lazy_list`**: The **Abyss Gazer**. Audit your entire backlog or just today's failures.
- **`lazy_done`**: Mark a task complete and receive brand-aligned validation.
- **`lazy_rename`**: **Revisionist History**. surgically update a task's description.
- **`lazy_move`**: Reschedule the inevitable with natural language grace.
- **`lazy_push`**: The **Global Panic Button**. Instantly push all today's burdens to tomorrow.
- **`lazy_get_messages`**: Audit the reservoir of LulzCorp whimsy.

---

## 🏛️ The Cyber-Baroque CLI

For those moments when you wish to feel the tactile crunch of the terminal. 

### 🕯️ The Core Workflow: "Smart Parsing"
`lazy` is designed to understand you even when you're barely trying. It uses a **Smart Parsing** heuristic that lets you mix multi-word descriptions and natural language dates without quotes, flags, or effort.

```bash
# No quotes. No "add" command. Just shout it at the terminal.
lazy Buy eggs tomorrow
lazy mv boxes to basement this weekend
lazy call mom next fri
```
*Result:* `lazy` handles the ambiguity, identifies the date, and saves the rest as the description.

### 📖 High-Status Rituals

#### 1. The Global Panic Button (Instant Relief)
Are there too many things on today's list? Do you feel the friction of reality? Push it all away.
```bash
lazy push
```
*(Alias: `p`)*. Instantly reschedules all of today's pending tasks to tomorrow. Relief is mandatory.

#### 2. The "Not Today" Button
Just one annoying task you want to ignore? Bump it.
```bash
lazy bump <id>
```
*(Alias: `b`)*. Moves a specific task to **Tomorrow**. If no ID is provided, it bumps the first item on the list.

#### 3. Do ONE Thing (The Focus Lens)
If you must work, work on the single most urgent item.
```bash
lazy focus
```
*(Aliases: `1`, `one`)*. This clears the screen and shows you exactly **one** task. Do it, or don't.

#### 4. Revisionist History (Editing the Past)
- **`lazy rename <id> <text>`**: Change a description to suit your current state of inertia. (Aliases: `rn`, `re`, `edit`).
- **`lazy view <id>`**: Isolate a single task to study it in its lonely glory. (Aliases: `v`, `show`).

---

## 🛠 Command Reference: The Manual of Inaction

| Command | Aliases | Description |
| :--- | :--- | :--- |
| `lazy` | | **List Today:** Shows only what is due today (and overdue). |
| `lazy l` | `list`, `ls` | **List All:** Shows the entire backlog sorted by date. |
| `lazy <text>` | `a`, `add`, `new` | **Add:** Just type the task. Dates are parsed automatically. |
| `lazy d <id>` | `done` | **Done:** Marks task `<id>` as complete. Prints praise. |
| `lazy m <id> <date>` | `mv`, `move` | **Reschedule:** Move a specific task to a new date. |
| `lazy rn <id> <text>` | `re`, `rename`, `edit` | **Rename:** Change the description of an existing task. |
| `lazy v <id>` | `view`, `show` | **View:** Display the full details of a single task. |
| `lazy b [id]` | `bump` | **Bump:** Moves a task to tomorrow (defaults to top task). |
| `lazy p` | `push` | **Push:** Moves ALL today's tasks to tomorrow. |
| `lazy 1` | `one`, `focus` | **Focus:** Displays exactly one urgent task. |
| `lazy t` | `triage` | **Triage:** Interactive loop to process today's tasks. |
| `lazy help` | `-h`, `--help` | **Help:** Shows usage information (doesn't add a task named "help"). |

---

## 📅 The "Vibes-Based" Time System

`lazy` knows that "Next Friday" is a feeling. It uses the **"Lazy Next" Algorithm** to handle your procrastination patterns.
- **"Friday"**: The upcoming Friday.
- **"Next Friday"**: Not this coming Friday, but the one after.
- **"EOW" / "EOM" / "EOY"**: End of Week (Fri), Month, or Year.
- **"Soon"** (+3d), **"Later"** (+1w), **"Someday"** (+1m).

---

## ⚙️ Systems & Architecture

- **Data Persistence:** A **SQLite** backend (`lazy.db`) ensures your tasks survive a reboot, even if your motivation doesn't. 
- **Verification:** A full regression suite ensures the machinery of inaction remains stable. Run `python3 test_lazy.py`.
- **Configuration:** `lazy/config.json` controls the aesthetic (colors) and the whimsical messages you receive.

---

*Now go take a nap. You've earned it by reading this.*
