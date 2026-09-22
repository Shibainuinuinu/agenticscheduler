# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A hand-written CLI agent that answers scheduling questions and manages calendar
events. **The point of the project is learning**, not shipping — see `PLAN.md` for
the full build order, file-by-file breakdown, and current status.

## Working mode — read this first

The user is a third-year CS major: solid on Python and general CS fundamentals,
newer to agents, LLM APIs, and OAuth. The goal is to *understand* the system —
its design and the reasoning behind it — not to memorize syntax.

- **Claude may write the code**, including `calendar_store.py` and `agent.py`.
  Rote syntax and API boilerplate aren't the learning target.
- **The learning target is design.** When writing or changing code, surface the
  decisions that matter: why this boundary, what the alternatives were, what
  the trade-off is, what breaks later if we choose wrong. Invite discussion on
  those before or alongside the code, rather than only explaining after.
- **Walk through what was written** — the shape and the non-obvious lines, not
  every line. Confirm the user understands the parts that carry weight.
- When the user writes code themselves, review it and explain corrections.
- **Do handle environment plumbing** — installs, venv, git, package management.
- Explain new concepts (LLM APIs, OAuth, Google's API model) as they come up.
- Prefer small working increments over large scaffolds; keep each one runnable.
- Record design decisions in `PLAN.md` as they're made.

## Environment

The project is worked on from two machines. Each has its own `.venv/`
(gitignored), so the layouts differ:

| | macOS (zsh) | Windows 10 (Git Bash) |
|---|---|---|
| Python | 3.11.5 | 3.13.14 |
| Run | `.venv/bin/python <script>` | `.venv/Scripts/python.exe <script>` |

Code must run on 3.11 — avoid 3.12+ only features. Editor settings
(`.vscode/`) are per-machine and gitignored. Pull before starting on either
machine; the other may have pushed.

## Provider

Gemini free tier — the user has a hard zero-spend constraint. **Do not suggest
paid APIs.**

- SDK: `google-genai` (installed)
- Model: `gemini-3.6-flash`
- Auth: `GEMINI_API_KEY` env var, read automatically by `genai.Client()`

The Interactions API (`client.interactions.create`) is newer than the model's
training data. **Verify field names against https://ai.google.dev/gemini-api/docs
before asserting them** rather than recalling from memory. Conversation state is
server-side by default via `previous_interaction_id`.

## Architecture

```
agent.py            loop + tool schemas + execute() dispatch
  ├── scheduling.py       ranks/filters slots by learned profile   (Step 8)
  │     └── profile.json     per-weekday hours, buffers, labels
  └── calendar_store.py   four calendar functions
        └── events.json   fake data
```

The boundary at `calendar_store.py` is load-bearing: its four function signatures
are frozen so that swapping the fake backend for real Google Calendar (Step 7)
requires **no change to `agent.py`**. If a change seems to need edits above that
line, the abstraction is wrong — say so rather than working around it.

Other invariants:

- **Date arithmetic, gap-finding, and conflict detection are Python, never the
  model.** The model chooses among options the code produced; it does not compute
  timestamps.
- **No agent frameworks.** The loop is written by hand on purpose.
- Events are naive local ISO strings at the `calendar_store.py` boundary. Step 7
  converts to/from Google's offset-aware times *inside* the store, so
  `agent.py` never sees a timezone.
- While developing Step 7, the store targets the "Agent Sandbox" calendar via
  `CALENDAR_ID`, never `"primary"`. OAuth scope is `calendar.events` only.
- The file is `calendar_store.py`, never `calendar.py` — the latter shadows the
  Python stdlib `calendar` module.
- **Personalization is policy, not storage.** Learned scheduling preferences live
  in `scheduling.py` / `profile.json`, above the store — never inside
  `calendar_store.py`, which gets swapped wholesale in Step 7 and would take them
  with it. `find_free_slots` returns mechanical gaps over a wide floor window;
  narrowing and ranking happen above it.
- `find_free_slots` returns a **list** (JSON-serialized into a `function_result`,
  so no generators) of `{"start", "end"}` dicts with **ISO string** values —
  matching the keys `create_event` takes, so the model copies rather than
  transforms. Whole gaps, not duration-sized slices. `[]` is a valid answer.
- The gap walk uses a **cursor** = "earliest moment still possibly free", advanced
  with `cursor = max(cursor, event_end)`. The `max` is load-bearing: events sort
  by *start*, so a nested event would otherwise move the cursor backwards.

## Conventions

- Secrets come from environment variables or gitignored files. Never hardcode a
  key, never commit one. Never print the contents of `credentials.json` or
  `token.json`.
- `.gitignore` covers `.venv/`, `__pycache__/`, `.env`, `.vscode/`,
  `credentials.json`, `token.json`.
- Offline tests (Step 6) were skipped by the user's choice; verification is by
  hand. Don't reintroduce them unless asked.
