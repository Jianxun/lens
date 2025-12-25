#
# Shared Lessons

This file stores persistent user preferences or rules that every agent must
follow before doing any work. Keep it concise, append-only, and user-driven:

- Only add a lesson when the user explicitly asks for a rule that applies to all
  agents.
- Never remove or alter an existing lesson unless the user revokes or replaces
  it.
- Reference this file at the start of every session (before reading the
  contract/tasks) so the latest preferences are honored.

## Active Lessons

1. **2025-12-20 — Always fetch the current date via the `date` command.**
   - Whenever a task needs "today's" date/time, run `date` in the shell and use
     that output instead of relying on cached or remembered values.

2. **2025-12-23 — Do not touch Docker unless explicitly instructed in the task.**
   - The database Docker container is always up when running tasks.
   - Never start, stop, restart, or check the status of Docker containers unless
     the task explicitly requires it.

3. **2025-12-25 — Load secrets from `.env` before running embedding-dependent commands.**
   - Source the repo `.env` (e.g., `set -a && source .env && set +a`) so `SUPER_MIND_API_KEY` is available for student portal embeddings and API verification.
