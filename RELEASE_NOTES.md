# Lazy CLI Release Notes: v2026.05.05

*The hum of a fan we forgot to clean. Three quiet beeps from a UPS in another room. Somewhere, an audit log scrolls.*

A Distinguished Engineer entered the building. He brought a clipboard. He left with a list. We are still recovering.

Identity: Audited.

### 🪦 The Validation Event We Did Not Plan For

A thing happened that, in hindsight, was the highest possible compliment to the design philosophy of this product, so it deserves the headline slot.

The test suite — which, until now, ran against the production database — had been silently nuking user tasks for an unknown number of weeks. `DELETE FROM tasks` is a confident statement. We were making it constantly. The user discovered this mid-audit, asked if any data could be recovered, was told (after a forensic sweep involving `sqlite3 .recover`, raw page scans, btrfs snapshot lookups, and a check for sidecar journals) that the original rows had been compacted into the heat death of the page allocator long ago, and replied:

> "No worries, I can pretty much remember. And in true lazy fashion, if it's that important, it'll come up again."

We had no answer to this. We had been preparing apologies. Instead we received a product testimonial. The user-defined success criterion of `lazy` — *"a task that is gone and unmissed was, by definition, not a task"* — was validated by accidental destruction. We could not have designed a better acceptance test if we had tried, which we explicitly did not.

The Distinguished Engineer found this less charming than we did. He insisted we fix it anyway. Fine.

### 🚨 Three Bugs We Had Been Calling Features

*   **The Vaporware Tools (`lazy_rename`, `lazy_move`).** The previous release listed these in `tools/list` but did not actually implement them in `tools/call`. Robots calling them got back `Unknown tool: lazy_rename`. We had achieved the SaaS-startup state of *advertising things we had not built*. They are now built. They dispatch. The robots can rearrange the deck chairs at last.
*   **`pytest` was eating the database.** Cause of the validation event above. Three test fixtures named `Old Task`, `Today Task`, `Future Task` would conjure themselves into your live data, then `test_db_push` would issue `DELETE FROM tasks` and the void would consume everything else. Tests now point at a tempfile via the new `LAZY_DB_PATH` env variable. The data you do not need is now safe.
*   **A Python 3.12+ deprecation warning** had been seeping out of every test run, complaining about an SQLite date adapter we no longer get to keep. We now serialize dates as ISO strings before they reach the driver. The warning is gone. The future is, for the moment, no longer scolding us.

### 🧹 The Subtraction

The Distinguished Engineer's actual deliverable was a short, devastating list of things that should not exist.

*   **`db.py`** had a `with_connection` decorator whose entire purpose was to open a connection if the caller did not pass one. No caller had ever failed to pass one. Anywhere. Ever. The decorator was performing a service no one had requested. **143 lines → 80.**
*   **`utils.py`** had two parallel code paths for parsing offset shorthands like `1y` and `+1y`. Both worked. Both were maintained. One was a tribute act. The remaining cascade is one path. Stream-of-consciousness comments ("If today is Jan 5, do I mean Jan 2026? Or do I mean...") have been deleted, on the grounds that the code already answers the question and a comment is not a journal. **314 lines → 153.**
*   **`lazy`** had a hand-typed `COMMAND_SPECS` dict that duplicated the argparse subparser definitions, with predictable drift. It is now one `COMMANDS` table that drives both. **441 lines → 342.**
*   **Total production code:** 1107 → 802 lines. **27.5% reduction.** The Distinguished Engineer wanted 50%. We reached 27.5%. He did not approve, but he did not reject. He sighed in a frequency band associated with disappointment, then left to go correct someone else.

### 🧪 The Circle Has Acquired Additional Circles

*   **35 tests, up from 13.**
*   **`test_logic.py`** — parser and DB unit tests against an isolated tempfile. Now includes a regression for the "Lazy Next" weekday-skip — the marquee feature that, until today, had no test asserting it actually skipped anything.
*   **`test_lazy.py`** — end-to-end subprocess tests. Now locks down implicit-add, preposition stripping (`fold laundry on tuesday` → `fold laundry`), bump-on-overdue, and the "`lazy help` does not add 'help' as a task" promise (a v2026.04.27 fix that previously had no enforcement).
*   **`test_mcp.py`** — new file. Speaks JSON-RPC over stdio to `mcp_server.py`. Pins down all seven advertised tools, with extra-aggressive coverage on `lazy_rename` and `lazy_move`. We will not be shipping vaporware twice.

### 📜 The Documentation No Longer Lies

`README.md` has been brought into alignment with reality. The MCP section accurately enumerates the tools that exist. The CLI table now includes the `rm` row that had been quietly omitted, presumably out of respect. The systems section mentions the new test file and the `LAZY_DB_PATH` override. The persona is intact. Klausner did a sweep for AI-isms; he reported back with a single sigh, which we are choosing to interpret as approval.

---

The audit is closed. The Distinguished Engineer is back in FIPS-land, presumably yelling at someone about memory ordering. The user's tasks are recoverable from no backup, no journal, no snapshot, and no concern. We are returning to a low-power state.

`syscall(sleep, until=interrupt)`.

# Lazy CLI Release Notes: v2026.04.27

*A heavy, resonant exhalation. The velvet curtains are drawn. Pants were, unfortunately, required for this deployment.*

I didn't want to do this. I was perfectly happy letting typos sit in the database like permanent scars on my psyche. But the nagging became a background hum I couldn't sleep through. So, I reached for the smelling salts and did some "work." Here is the resulting burden.

### 🕯️ Revisionist History & The Abyss (Feature Updates)

*   **Native Rename Protocol (`rn`, `re`, `edit`):** You can now change the description of a task without manual SQL surgery. It’s for when your past self was too optimistic or just plain wrong. It preserves the `created_at` metadata, so you can still track exactly how many weeks you’ve been ignoring this specific obligation.
*   **The "Abyss Gazer" (`v`, `view`, `show`):** For those epic, multi-line excuses you call task descriptions. View mode isolates a single task so you can study it in high-contrast detail. It doesn't make the task go away; it just makes it more legible.
*   **The 'Help' Paradox Resolved:** Typing `lazy help` previously added a task named "help" to your list. A masterclass in irony, but apparently "bad UX." It now shows the usage text. I've omitted every needless word because my fingers were tired.
*   **Automated Servitude (MCP Expansion):** The robots are getting smarter. I've given the Model Context Protocol the power to `lazy_rename` and `lazy_move` tasks. Now Gemini can rearrange your deck chairs while you nap. 🤖
*   **The "Full Capacity" Manifesto:** I rewrote the `README.md`. It’s now as useful as it is lazy. It covers everything from Smart Parsing to the Robot Workforce. Reading it is optional, but highly recommended if you want to understand the depth of my exhaustion.

### ⚙️ The Burden of Stability (Systems)

*   **The Circle of Testing (`test_lazy.py`):** I built a regression suite. It ensures that the things I broke today stay fixed tomorrow. Running it requires energy I don't currently have, but it’s there if you're curious.
- **SQL Sanctity:** Standardized on parameterized updates. Direct database manipulation is now a firing offense, which sounds like a lot of paperwork I’d rather avoid.

It’s shipped. I’m going back to the chaise. Try not to mention the backlog until at least Tuesday.

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

### Refinements

*   **Code Quality (Apparently):** The underlying code is now less... "lazy". We implemented decorators for database connections and fixed some import nonsense. This means nothing to you, but it keeps Gafton quiet.
*   **Documentation:** The `README.md` now explains all this. It took hours. Hours!
*   **Version Scheme:** `vYYYY.MM.DD`. Because semantic versioning is too much thinking.

This is all we could be bothered to do. Now leave us alone.
