# Lazy 🦥
**The Task Manager for People Who Hate Task Managers**

> "Why do today what you can push to tomorrow?"

`lazy` is a zero-friction, CLI-based task manager built on a single core philosophy: **Guilt is useless.**

Most todo apps are designed to make you feel bad about your growing backlog. `lazy` is designed to help you aggressively defer, ignore, and eventually (maybe) complete tasks, while telling you that you're doing a great job.

## 🚀 Getting Started

You have to type very little. That is the point.

This tool is a spiritual successor to an ancient legend: **LazyMeter**. Back in 2011, LazyMeter was the only to-do list other than pen and paper that truly understood the procrastinator's soul. It vanished, lost to the sands of time (and probably someone being too lazy to renew the domain). Until now. Thanks to Gemini, `lazy` rises from the ashes, built on the very principles of its forebear, because some things are just too good to stay gone... even if it took over a decade.

```bash
# Run directly
./lazy/lazy

# Recommended: Add alias to your .bashrc or .zshrc
alias lazy="~/gemini/lazy/lazy"
```

## 📖 The "Lazy" Workflow

### 1. Dump Your Brain
Don't worry about dates. If you don't specify one, it defaults to **Today**.
You don't even need to type "add" or "a". Just type the task. No quotes needed.

```bash
lazy Buy Milk
lazy Call Mom tmw
lazy Fix the roof eventually
```

**The Killer Feature (Smart Parsing):**
You can mix command words, multi-word descriptions, and multi-word dates. `lazy` figures it out.

```bash
# "mv" is a command? No, here it's part of the task!
# "this weekend" is a date? Yes!
lazy mv boxes to the basement this weekend
```
*Result:* Adds task **"mv boxes to the basement"** due **Next Saturday**.

```bash
# "ls" is a command? No!
lazy ls my files next mon
```
*Result:* Adds task **"ls my files"** due **Next Monday**.

### 2. Check the Damage
Run `lazy` to see *only* what is due today (or overdue). Ignore the future. The future is a problem for Future You.
```bash
lazy
```

### 3. The "Panic Button"
Are there too many things on today's list? Do you feel overwhelmed?
**Push everything to tomorrow.**
```bash
lazy push
```
*Effect:* Instantly reschedules all of today's pending tasks to tomorrow. 
*Feeling:* Instant relief.

### 4. Do ONE Thing
If you must work, work on the single most urgent item.
```bash
lazy focus
```
*(Alias: `lazy 1`)*. This clears the screen and shows you exactly **one** task. Do it, or don't.

---

## 📅 The "Vibes-Based" Time System

`lazy` understands that "Next Friday" is a feeling, not a coordinate.

### The "Lazy Next" Algorithm
If today is Thursday, and you say "Next Friday", standard calendars think you mean tomorrow.
**Lazy people know that "Next Friday" means "Not this coming Friday, but the one after."**

`lazy` enforces this.
*   **"Friday"**: The upcoming Friday.
*   **"Next Friday"**: The Friday of next week.
*   **"Weekend"**: The upcoming Saturday.
*   **"Next Weekend"**: The Saturday of next week.

### Vague Timeframes
Because specific dates are stressful.

*   `soon` → +3 days
*   `later` → +1 week
*   `weekend` → Next Saturday
*   `someday` / `eventually` → +1 month

### Standard Offsets
*   `today`, `tmw`, `yesterday`
*   `+1` (1 day), `+1w` (1 week), `+1m` (1 month)
*   `mon`, `tue`, `wed`... (Finds the next occurrence)
*   `eow` (End of Week / Fri), `eom` (End of Month), `eoy` (End of Year)

---

## 🛠 Command Reference

| Command | Alias | Description |
| :--- | :--- | :--- |
| `lazy` | | **Focus Mode:** Lists tasks due **today** (and overdue). |
| `lazy l` | `ls` | **List All:** Shows the entire backlog sorted by date. |
| `lazy "Task"` | `a`, `new` | **Add:** Just type the task. Dates are parsed automatically. |
| `lazy d <id>` | | **Done:** Marks task `<id>` as complete. Prints praise. |
| `lazy rm <id>` | `del` | **Delete:** Permanently removes task `<id>`. |
| `lazy p` | `push` | **Push:** Moves all today's tasks to tomorrow. |
| `lazy 1` | `focus` | **One Thing:** Shows the single most urgent task. |
| `lazy t` | `triage` | **Triage:** Interactive mode to process today's tasks. |
| `lazy m <id> <date>` | `mv` | **Reschedule:** Move a specific task. |

---

## ⚙️ Configuration

`lazy/config.json` allows you to customize the experience.

```json
{
  "enable_colors": true,        // Red for overdue, Green for today
  "empty_state_messages": [ ... ], // What it says when you have nothing to do
  "completion_messages": [ ... ]   // The validation you crave when you finish a task
}
```

---

*Now go take a nap.*