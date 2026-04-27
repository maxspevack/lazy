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
- `lazy_rename`: Revisionist History. Change the past until it’s less tiring.
- `lazy_move`: Reschedule the inevitable.

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
*Result:* `lazy` figures out what is the task and what is the date. It’s smarter than I am, which isn't saying much today.

### 📖 High-Status Rituals

#### 1. The Global Panic Button (Instant Relief)
Are there too many things on today's list? Do you feel the friction of reality? Push it all away.
```bash
lazy push
```
*(Alias: `p`)*. Instantly moves everything due today to tomorrow. It’s the closest thing to a "Delete Reality" button we have.

#### 2. The "Not Today" Button (The Bump)
Just one annoying task you want to ignore? Bump it.
```bash
lazy bump <id>
```
*(Alias: `b`)*. Moves a specific task to **Tomorrow**. If no ID is provided, it bumps the first item on the list.

#### 3. Do ONE Thing (The Focus Lens)
If you're being forced to work, just look at **one** thing. Looking at the whole list is a health hazard.
```bash
lazy focus
```
*(Aliases: `1`, `one`)*. It clears the screen and shows you exactly **one** task. Do it, or don't.

#### 4. Revisionist History (Editing the Past)
- **`lazy rename <id> <text>`**: Change a description to suit your current state of inertia. (Aliases: `rn`, `re`, `edit`).
- **`lazy view <id>`**: Isolate a single task to study it in its lonely glory. (Aliases: `v`, `show`).

---

## 🛠 The Manual of Inaction (Command Reference)

I'm only writing this table once. Please don't make me do it again.

| Command | Aliases | The Minimal Effort Required |
| :--- | :--- | :--- |
| `lazy` | | Lists today's failures (and overdue ones). |
| `lazy l` | `list`, `ls` | Shows the entire scroll of judgment (sorted). |
| `lazy <text>` | `a`, `add`, `new` | Add a task. Or don't. I'm not your boss. |
| `lazy d <id>` | `done` | Mark it done. Get a gold star. Go back to sleep. |
| `lazy m <id> <date>` | `mv`, `move` | Reschedule. Natural language (tmw, fri) supported. |
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
- **Relative:** `today` (`tod`), `tomorrow` (`tmw`, `tom`).
- **Offsets:** `+1`, `2w`, `3m`, `1y` (works with or without the `+`).
- **The "Lazy Next":** `next fri` skips the one coming up too fast and picks the one after.
- **Milestones:** `eow` (End of Week), `eom` (End of Month), `eoy` (End of Year).
- **Vague Potentials:** `soon` (+3d), `later` (+7d), `someday` / `eventually` (+1m).

---

## ⚙️ The Boring Stuff (Systems)

- **Persistence:** Uses **SQLite** (`lazy.db`). Your tasks survive a reboot. My motivation doesn't.
- **Verification:** There’s a test suite (`test_lazy.py`). Run it if you're bored.
- **Config:** `lazy/config.json`. You can change the colors and the sarcastic messages. 

---

*I’m going back to the chaise. If you need me, don’t.*
