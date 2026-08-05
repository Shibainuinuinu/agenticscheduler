# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

A hand-written CLI agent that answers scheduling questions and manages calendar
events. **The point of the project is learning**, not shipping — see `PLAN.md` for
the full build order, file-by-file breakdown, and current status.

## Working mode — read this first

The user is a third-year CS student with no prior agent/LLM/OAuth experience. The
explicit goal is to *understand* the code, not to have it produced for them.

- **Explain the concept and what the code must do; let the user write it.** Then
  review and explain any corrections.
- **Do not write implementation files** (`calendar_store.py`, `agent.py`,
  `test_agent.py`) unless the user directly asks.
- **Do handle environment plumbing** — installs, venv, package management. That
  isn't what they're here to learn.
- Explain new concepts as they come up; assume no familiarity with LLM APIs.
- Prefer small working increments over large scaffolds.

## Environment

- Windows 10, **Git Bash** (not PowerShell/cmd) is the user's shell
- Python 3.13.14 at `%LOCALAPPDATA%\Programs\Python\Python313`
- venv at `.venv/` — Windows layout, so `.venv/Scripts/` not `.venv/bin/`
- Run scripts with `.venv/Scripts/python.exe <script>`, or
  `source .venv/Scripts/activate` first

A Python 3.10 also exists on the machine. Only 3.13 is on PATH; the venv makes it
moot.

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
- Events are naive local ISO strings; timezone-awareness is deferred to Step 7.
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

- Secrets come from environment variables. Never hardcode a key, never commit one.
- `.gitignore` covers `.venv/`, `__pycache__/`, `.env`.
- Tests use a stubbed client and must run offline with no network calls.
