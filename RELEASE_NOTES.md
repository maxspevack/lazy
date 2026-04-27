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
