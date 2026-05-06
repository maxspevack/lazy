# Lazy 🦥
**The Task Manager for the Profoundly Exhausted**

> *Sigh.* "Why do today what you can... actually, just don't."

Listen, I didn't want to build this. Building things requires focus, and focus is just a fancy word for "unpaid labor I do for my own brain." But the friction of life—the nagging, the "to-do" lists that look like scrolls of judgment—it became more exhausting to ignore than to fix. 

So, I built `lazy`. It’s a zero-friction, CLI-based task manager for people who find the act of opening a mobile app to be a Type 1 hurdle. It’s for people who know that **Guilt is useless** and that a nap is always a viable strategic pivot.

## 🤖 The Elite Interface: AI-First (MCP)
**The "I Can't Even" Interface**

If you're truly one of us, you won't even use the CLI. Typing is manual labor. `lazy` includes a **Model Context Protocol (MCP)** server so you can just mumble at an AI (like Gemini) and have *it* handle the burden of your existence. 

It’s the elite way to procrastinate. The robots do the tracking; you do the resting.

### Agentic Burden-Sharing:
- `lazy_add`: Manifest a task from the void.
- `lazy_list`: Gaze into the abyss of your obligations.
- `lazy_done`: Receive brand-aligned validation for the bare minimum.
- `lazy_push`: The Global Panic Button. Instant relief.
- `lazy_rename`: Revisionist history. Edit the past until it’s less tiring.
- `lazy_move`: Reschedule the inevitable.
- `lazy_get_messages`: Audit the brand. Inspect the LulzCorp catechism.

---

## 🏛️ The CLI (For when the smelling salts kick in)

If you absolutely must interact with a terminal, I've tried to make it as painless as possible. I omitted every needless keystroke because my fingers were tired.

### 🕯️ Smart Parsing (The "Just Shout at It" Method)
`lazy` is designed to understand you even when you're barely coherent. You don't need quotes. You don't need the `add` command. You don't need to put on pants.

```bash
# Just shout it at the terminal.
lazy Buy eggs tomorrow
lazy Call in dead fri
lazy mv boxes to basement this weekend   # Note the clever parsing of mv
lazy Audit my life choices soon          # +3 days of peace
lazy Stare into the void later           # +1 week of silence
lazy Pay the bills eom                   # End of Month
lazy Fix the coffee machine next weekend # Skip this Sat, pick the one after
lazy Reorganize the chaise 2w            # 2 weeks from now
lazy Check if I still have a pulse 1m    # 1 month from now
lazy cancel gym eventually               # +30 days (standard procrastination)
```
*Result:* `lazy` figures out what is the task and what is the date. It’s smarter than I am, which isn't saying much today. Trailing prepositions (`on`, `at`, `in`, `for`) get quietly stripped, so `lazy fold laundry on tuesday` stores `fold laundry`, not `fold laundry on`.

### 📖 High-Status Rituals

#### 1. The Global Panic Button (Instant Relief)
Are there too many things on today's list? Do you feel the friction of reality? Push it all away.
```bash
lazy push
```
*(Alias: `p`)*. Instantly moves everything due today (and overdue) to tomorrow. It’s the closest thing to a "Delete Reality" button we have.

#### 2. The "Not Today" Button (The Bump)
Just one annoying task you want to ignore? Bump it.
```bash
lazy bump <id>
```
*(Alias: `b`)*. Moves a specific task to **Tomorrow**. If no ID is provided, it bumps the first item on today's list. Bumping an *overdue* task lands tomorrow, not yesterday-plus-one. Whoever wrote the original logic was thinking ahead. I won’t name names.

#### 3. Do ONE Thing (The Focus Lens)
If you're being forced to work, just look at **one** thing. Looking at the whole list is a health hazard.
```bash
lazy focus
```
*(Aliases: `1`, `one`)*. It clears the screen and shows you exactly **one** task. Do it, or don't.

#### 4. Revisionist History (Editing the Past)
- **`lazy rename <id> <text>`**: Change a description to suit your current state of inertia. (Aliases: `rn`, `re`, `edit`).
- **`lazy view <id>`**: Isolate a single task to study it in its lonely glory. (Aliases: `v`, `show`).
- **`lazy rm <id>`**: Permanently obliterate a task. (Aliases: `remove`, `del`, `delete`). Use sparingly. Deletion is for tasks so embarrassing they cannot be allowed to persist in the audit trail.

#### 5. Triage (For the Forced March)
```bash
lazy triage
```
*(Alias: `t`)*. Single-key interactive loop over today's list: `(d)`one, `(b)`ump, `(p)`ush all, `(s)`kip, `(q)`uit. The minimum-friction path through the obligations you couldn't avoid.

---

## 🛠 The Manual of Inaction (Command Reference)

I'm only writing this table once. Please don't make me do it again.

| Command | Aliases | The Minimal Effort Required |
| :--- | :--- | :--- |
| `lazy` | | Lists today's failures (and overdue ones). |
| `lazy l` | `list`, `ls` | Shows the entire scroll of judgment (sorted). |
| `lazy <text>` | `a`, `add`, `new` | Add a task. Or don't. I'm not your boss. |
| `lazy d <id>` | `done` | Mark it done. Get a gold star. Go back to sleep. |
| `lazy rm <id>` | `remove`, `del`, `delete` | Obliterate. The void accepts your offering. |
| `lazy m <id> <date>` | `mv`, `move`, `reschedule` | Reschedule. Natural language (tmw, fri) supported. |
| `lazy rn <id> <text>` | `re`, `rename`, `edit` | Rename. Because you misspoke earlier. |
| `lazy v <id>` | `view`, `show` | View details. For when the description is a novel. |
| `lazy b [id]` | `bump` | Pushes one task to tomorrow. |
| `lazy p` | `push` | Pushes ALL today's tasks to tomorrow. *Heaven.* |
| `lazy 1` | `one`, `focus` | Shows exactly one task. Just one. |
| `lazy t` | `triage` | Interactive mode. It asks questions. I hate it. |
| `lazy help` | `-h`, `--help` | Shows this again. I can't believe I'm still typing. |

---

## 📅 The "Vibes-Based" Time System

"Next Friday" is a feeling. The **"Lazy Next" Algorithm** knows that. Standard calendars are for people who like meetings; `lazy` is for people who like naps.

### The Liturgy of Keywords:
- **Relative:** `today` (`tod`), `tomorrow` (`tmw`, `tom`), `yesterday`.
- **Offsets:** `+1`, `2w`, `3m`, `1y` (works with or without the `+`).
- **Fuzzy:** `in 3 days`, `5 days`, `in 2 weeks`, `2 months`. As if you can't be bothered with the pluses.
- **The "Lazy Next":** `next fri` skips the one coming up too fast and picks the one after.
- **Milestones:** `eow` (End of Week → Friday), `eom` (End of Month), `eoy` (End of Year).
- **Weekend Logic:** `weekend` / `this weekend` (next Saturday), `next weekend` (the Saturday after that).
- **Calendar Drift:** `next week`, `next month`, `next year`.
- **Months:** `jan` … `dec` (full or short) → 1st of the next occurrence.
- **Vague Potentials:** `soon` (+3d), `later` (+7d), `someday` / `eventually` (+30d).
- **Explicit:** `2026-12-17`, `12-17`, `12/17`, `17.12`. For when "soon" feels too aggressive.

If `parse_date` can't make sense of a string, it raises a `ValueError`. The CLI catches it and prints the error. Your faith remains intact.

---

## ⚙️ The Boring Stuff (Systems)

- **Persistence:** Uses **SQLite** (`lazy.db`, next to the script). Your tasks survive a reboot. My motivation doesn't.
- **DB override:** Set `LAZY_DB_PATH=/some/path` to redirect the database. The test suite uses this to avoid eating your real tasks. Yes, that *was* a bug. Yes, it's fixed.
- **Verification:** Three test files. `test_logic.py` (parser + DB unit), `test_lazy.py` (end-to-end CLI subprocess), `test_mcp.py` (JSON-RPC over stdio). `python3 -m pytest`. Run them if you're bored. They use a tempfile DB and won't touch yours.
- **Config:** `lazy/config.json`. You can change the colors and the sarcastic messages. The schema is: `enable_colors` (bool), `completion_messages` (list[str]), `empty_state_messages` (list[str]), `add_echo_messages` (list[str], with `{description}` and `{date}` placeholders).

---

*I’m going back to the chaise. If you need me, don’t.*
