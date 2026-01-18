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
