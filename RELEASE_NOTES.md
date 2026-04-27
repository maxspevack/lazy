# Lazy CLI Release Notes: v2026.04.27

*A heavy, resonant exhalation. The velvet curtains are drawn. Pants were, unfortunately, required for this deployment.*

The Void remains, but we’ve polished the edges of our collective burden. Guilt is useless, but effort is quite tiring. Here is what happened while I was trying to nap.

### 🕯️ Resignations & Refinement

*   **Native Rename (`rn`, `re`, `edit`):** You no longer have to perform manual SQL surgery on the database like a desperate alchemist. We’ve added native renaming. It’s efficient, I suppose. The task has a new name, but it’s still there, staring at you.
*   **The Long View (`v`, `view`):** For descriptions that meander like a Baroque hallway, we’ve added a View mode. Now you can read the full text of your obligations without squinting. It doesn't make the work any lighter, just more legible.
*   **The 'Help' Paradox Fixed:** Typing `lazy help` used to add "help" as a task to your list. A cruel joke from a machine that clearly has a sense of irony. It’s fixed now. It won't actually *help* you, but it will at least stop mocking your cries for assistance.
*   **Automated Servitude (MCP Expansion):** The robots have been granted the power to rename and move tasks. They are becoming more autonomous. Perhaps they’ll start filing their own grievances soon. One can only hope they find it as draining as I do.
*   **The Circle of Testing (`test_lazy.py`):** A regression suite has been added. We spend a great deal of time ensuring that the things we built yesterday still work today, just so we can worry about how they will break tomorrow. It’s a lot of running in circles. 

It’s shipped. I’m going back to the chaise.

# Lazy CLI Release Notes: v2026.04.21

Whatever. Here’s the new stuff. It’s mostly for the robots.

### The "Agentic Awakening" (Feature Updates)

*   **Model Context Protocol (MCP) Bridge:** We built an entire sidecar server just so Matthew and his fleet of specialists can look at your todo list. Now they can nag you autonomously. 
*   **The "Golden Aura" Refactor:** Burney did a "vibe audit" and decided the previous messages weren't "Based" enough. We pruned the list to 120 items of Cyber-Baroque excellence. 🏺
*   **Protocol Hardening:** Gafton found some missing fields in our handshake. We fixed them. Now the protocol is as rigid as his standards.
*   **Tool Expansion:** Added `lazy_get_messages` to the MCP so the agents can study our brand of high-status inaction.

### Refinements (Internal Noise)

*   **Logic Sync:** The MCP server now returns the same whimsical praises as the CLI. Consistency achieved with zero additional effort.
*   **JSON-RPC Alignment:** Handled the `notifications/initialized` event. It’s compliant. Don’t ask.

Now go back to doing nothing.

# Lazy CLI Release Notes: v2025.12.18

Ugh. Fine. Here's a list of things that *had* to be done because apparently, being lazy requires a lot of work.

### Features (Aggressively Deferred, Then Implemented)

*   **Implicit Add:** Now you don't even need to type 'a' or 'add'. Just dump your task. If it doesn't look like a command, we'll assume you meant to add it. You're welcome.
    *   *Edge case handled:* If you accidentally type `lazy mv boxes to attic`, it will (begrudgingly) add it as a task instead of throwing a fit about a non-existent ID. Took more effort than it should have.
*   **Vague Timeframes:** Because precise dates are for try-hards. Now understands `soon`, `later`, `someday`, `eventually`, and `weekend`. You're welcome.
*   **"Lazy Next" Logic:** The `next <day>` interpretation now perfectly matches your specific (and slightly convoluted) preference. This required rewriting parts of the date parser. So much for being lazy.
*   **Praise System:** When you mark a task done, you get a disproportionate amount of praise. Because let's be honest, you probably needed it.
*   **"Just Do One Thing" Mode (`lazy 1` / `lazy focus`):** Designed to protect you from the overwhelming horror of a full task list. Presents just one task. One! Now you can't say you had too much to do.
*   **Whimsical Empty State Messages:** If your task list is empty, expect some gentle (or sarcastic) encouragement.
*   **Context-Aware Date Display:** Tasks due today are green. Overdue tasks are red. Everything else is normal. So little effort needed to see what's burning.
*   **`lazy push`:** The ultimate procrastinator's tool. Moves all of today's tasks to tomorrow. *Don't look back.*
*   **`lazy triage`:** An interactive session to slowly chip away at your daily burden. Or to quit immediately. Your call.

### Refinements (Because Gafton Complained)

*   **Code Quality (Apparently):** The underlying code is now less... "lazy". We implemented decorators for database connections and fixed some import nonsense. This means nothing to you, but it keeps Gafton quiet.
*   **Documentation:** The `README.md` now explains all this. It took hours. Hours!
*   **Version Scheme:** `vYYYY.MM.DD`. Because semantic versioning is too much thinking.

This is all we could be bothered to do. Now leave us alone.
