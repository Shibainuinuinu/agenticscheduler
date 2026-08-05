# Calendar + Schedule Agent — Project Plan

A learning project: build a tool-calling LLM agent from scratch, by hand, with no
agent frameworks. The build order below is deliberate — each step adds one
concept and stays runnable.

Assistant working mode and environment details live in `CLAUDE.md`.

## Goal

A command-line agent that answers scheduling questions and manages calendar
events. Example requests:

- "What's on my Wednesday?"
- "Find me two hours for deep work this week and block it."
- "Move my Thursday afternoon meeting to Friday morning."

---

## Where I am right now

| Step | Status |
|---|---|
| 0. Environment setup | ✅ done — smoke test passes |
| 1. `calendar_store.py` + `events.json` | ✅ done — all four functions verified in the REPL |
| 2. Agent loop with `list_events` | ⬜ |
| 3. Add `find_free_slots` + `create_event` | ⬜ |
| 4. Step limits, error handling, trace log | ⬜ |
| 5. Confirmation before writes | ⬜ |
| 6. Offline tests | ⬜ |
| 7. Real Google Calendar (OAuth) | ⬜ |
| 8. Learned scheduling profile | ⬜ — designed, not started |

Done so far: Python 3.13.14 installed, `.venv` created, `google-genai` installed,
git initialized, `.gitignore` written. `events.json` written. `list_events`,
`create_event`, `delete_event` written and working.

**Current task — Step 2, the agent loop.** `calendar_store.py` is complete and
verified against nested, overlapping, back-to-back, empty-day, and cross-midnight
cases.

One contract worth remembering: **`find_free_slots`'s `end_date` is inclusive of
the whole final day; `list_events`'s is exclusive.** They deliberately differ, and
`find_free_slots` bridges the two by passing `list_events` midnight after the last
day. Comparing ISO strings instead of parsed `datetime`s is what originally hid
this — everything now parses before comparing.

---

## The files, and what each one is for

Nothing here exists yet except `.gitignore` and this file. Each gets created at
the step listed.

| File | Created in | What it is |
|---|---|---|
| `.gitignore` | ✅ done | Tells git to ignore `.venv/`, `__pycache__/`, `.env` — things that shouldn't be in version control |
| `smoke.py` | ✅ done | Six lines. Proves the API key and install work *before* any agent complexity exists. Throwaway. |
| `events.json` | ✅ done | Fake calendar data. A JSON list of events. This is the "database". |
| `calendar_store.py` | 🔨 Step 1 | The four calendar operations, reading/writing `events.json`. **Zero LLM code.** Later swapped for real Google Calendar without the agent noticing. |
| `agent.py` | Step 2 | The agent loop, the tool schemas, and the dispatch function. The heart of the project. |
| `test_agent.py` | Step 6 | Tests that run offline using a fake model, so the suite costs nothing and never flakes on the network. |
| `scheduling.py` | Step 8 | Ranks and filters the raw gaps from `find_free_slots` using the learned profile. Policy, not storage — deliberately *not* in `calendar_store.py`. |
| `profile.json` | Step 8 | The learned artifact: per-weekday working hours, buffers, title labels. Hand-editable. |

**Why `calendar_store.py` and not `calendar.py`:** Python has a built-in module
named `calendar`. A local file with that name shadows it, and anything that
imports the real one breaks in a confusing way. Renamed to dodge that.

---

## Provider: Gemini (free tier)

Zero-spend constraint, so this uses Gemini's free tier rather than a paid API.

- SDK: `google-genai` (installed)
- Env var: `GEMINI_API_KEY` — get a free key at https://aistudio.google.com/apikey
- Model: `gemini-3.6-flash`

The concepts are provider-independent: tools are name + description + JSON Schema,
the model never sees your Python, *your* code executes the call, and you loop until
the model stops asking. Only surface syntax differs between providers.

**One difference worth knowing:** Gemini keeps conversation history **server-side**
— you chain turns by passing `previous_interaction_id`. Anthropic-style APIs are
stateless and make you resend the whole transcript each turn. Both models exist in
the real world; we use Gemini's stateful path and discuss the other when we get there.

---

## Core design decisions

1. **Fake calendar first.** All calendar operations go through `calendar_store.py`,
   backed by a local JSON file. The real Google Calendar API is swapped in later
   behind the *same function signatures*. The agent code must not change when that
   swap happens.
2. **Logic in Python, judgment in the model.** Date arithmetic, gap-finding, and
   conflict detection are ordinary Python. The model decides *which* returned slot
   best fits the request. Never ask the model to compute timestamps.
3. **Write the agent loop by hand.** No agent frameworks. The loop is ~40 lines and
   understanding it is the point of the project.
4. **CLI only.** No web UI until the loop is solid.
5. **Timezones:** all events are naive local ISO strings for now. Timezone-awareness
   is deferred to the Google Calendar swap — noted here so it isn't a surprise.

---

## Step 0 — Environment (nearly done)

Remaining:

1. Get a free key at https://aistudio.google.com/apikey
2. Set it (Git Bash, in the project directory):
   ```bash
   export GEMINI_API_KEY="paste-key-here"     # this shell
   setx GEMINI_API_KEY "paste-key-here"       # future shells
   ```
3. Write `smoke.py`:
   ```python
   from google import genai

   client = genai.Client()
   interaction = client.interactions.create(
       model="gemini-3.6-flash",
       input="Say hi in five words.",
   )
   print(interaction.output_text)
   ```
4. Run it: `.venv/Scripts/python.exe smoke.py`

**Checkpoint:** it prints a greeting.

---

## Step 1 — `calendar_store.py` + `events.json`

No LLM involved at all. Pure Python you can poke at in the REPL.

**`events.json`** — a list of ~8 events across one week:
```json
[
  {"id": "1", "title": "Standup", "start": "2026-08-05T09:00", "end": "2026-08-05T09:15"}
]
```

**`calendar_store.py`** — four functions. These signatures are **frozen now**,
because the whole point is that swapping in real Google Calendar later changes
nothing above this file:

| Function | Returns |
|---|---|
| `list_events(start_date, end_date)` | events overlapping that range |
| `find_free_slots(start_date, end_date, duration_minutes)` | candidate gaps long enough to fit |
| `create_event(title, start, end)` | the new event, with a fresh id |
| `delete_event(event_id)` | confirmation, or raises if not found |

Concepts covered here: `datetime.fromisoformat`, sorting intervals, the gap-finding
algorithm, and why working-hours clamping belongs in Python rather than in the prompt.

### The gap-finding algorithm (settled)

Outer loop over calendar days, inner **cursor walk** per day:

```
for each day in [start_date, end_date]:
    day_start = that day at WORK_START_HOUR
    day_end   = that day at WORK_END_HOUR
    day_events = events overlapping [day_start, day_end], clamped to it, sorted by start
    cursor = day_start
    for event in day_events:
        if event_start > cursor:  candidate gap (cursor, event_start)
        cursor = max(cursor, event_end)
    candidate gap (cursor, day_end)
```

`cursor` = "the earliest moment still possibly free." **`max`, not plain
assignment** — events are sorted by *start*, so a nested event (09:00–17:00
workshop containing a 10:00–10:30 sync) would otherwise drag the cursor backwards
and report the workshop's hours as free.

The cursor replaces three separate branches: before-first falls out of
initializing `cursor = day_start`, after-last is the trailing line, and an empty
day runs zero iterations and emits the whole window.

### Return shape (frozen)

A **list** (not a generator — it gets JSON-serialized into a `function_result`)
of dicts with exactly `start` and `end` as **ISO strings**:

```python
[{"start": "2026-08-05T09:15", "end": "2026-08-05T11:00"}]
```

Same keys `create_event` accepts, so the model copies strings across rather than
transforming them. Whole gaps, not duration-sized slices. `[]` when nothing fits
— that's a normal answer, not an error. Parse to `datetime` on the way in,
`.isoformat()` on the way out.

### Bugs hit while writing this (for the README)

1. `import datetime` (module) but calling `datetime.fromisoformat`, which lives on
   the *class*. Instant `AttributeError`.
2. `res = []` and `return res` both indented inside the loop — returned at most
   one slot, and `[]` if the first gap was too short.
3. Subtracting ISO **strings** and calling `.total_seconds()` on the result.
4. Building day bounds by adding days to `start_date` itself, so a `start_date`
   with a time component skewed every day. Fixed with `.replace(hour=...)`.
5. `day_events[-1]['end']` assumed the last-*starting* event ends last. A nested
   event breaks it → replaced by the cursor walk.
6. Day filter used `event.start.date() == day`, dropping events spilling in from
   the previous day. Fixed with an overlap test plus clamping.
7. **The subtle one.** `list_events` compared ISO strings lexicographically, so
   `"2026-08-07T09:00" >= "2026-08-07"` was true and every event on the final day
   vanished — that day then reported as entirely free. Two causes: string
   comparison, and the inclusive/exclusive mismatch between the two functions.
   Both fixed. This is why timestamps get parsed before comparison, always.

**Checkpoint:** ✅ all four called from the REPL; nested, overlapping,
back-to-back, empty-day, and cross-midnight cases all verified. Still no agent.

---

## Step 2 — The agent loop, `list_events` only

New file `agent.py`. This is the main learning objective.

**Tools exposed to the model** — the model sees only these three fields per tool,
never your Python:

| Tool | Parameters |
|---|---|
| `list_events` | `start_date`, `end_date` |
| `find_free_slots` | `start_date`, `end_date`, `duration_minutes` |
| `create_event` | `title`, `start`, `end` |
| `delete_event` | `event_id` |

Start with `list_events` alone; add the others in Step 3.

**The loop:**

```python
interaction = client.interactions.create(
    model="gemini-3.6-flash", input=user_request, tools=TOOLS
)
for _ in range(MAX_STEPS):
    calls = [s for s in interaction.steps if s.type == "function_call"]
    if not calls:                      # model answered in words → done
        return interaction.output_text
    results = [execute(c) for c in calls]
    interaction = client.interactions.create(
        model="gemini-3.6-flash",
        input=results,
        tools=TOOLS,
        previous_interaction_id=interaction.id,
    )
```

Key ideas:
- The response has a `.steps` list. Steps of type `function_call` carry `.name`,
  `.arguments`, `.id`.
- Results go back as `function_result` steps whose `call_id` matches the request's
  step id. **Every call needs exactly one result.**
- The model doesn't *do* anything — it asks. `execute()` is where actions happen,
  which is why authorization lives there (Step 5).

**Checkpoint:** `python agent.py "what's on my Wednesday?"` works end to end.

---

## Step 3 — Add `find_free_slots` and `create_event`

Mechanical once the loop is right — this is the payoff. If the model starts
inventing timestamps, the fix is a more prescriptive tool description, not loop code.

**Checkpoint:** "Find me two hours for deep work this week and block it" works.

---

## Step 4 — Robustness

- `MAX_STEPS = 10` so a confused model can't loop forever.
- Wrap `execute()` in try/except. On exception, **return the error text as the
  function result** instead of crashing. The model usually self-corrects — prove
  this deliberately by feeding it a bad date.
- Trace log: print every tool name, its arguments, and its result. This is how you
  debug agents; without it you're guessing.

---

## Step 5 — Confirmation before writes

Gate `create_event` and `delete_event` behind a y/n prompt inside `execute()`. On
"n", return a normal (non-error) result saying the user declined.

---

## Step 6 — Offline tests

`pytest` with a fake client whose `interactions.create` returns canned responses.
No network in the test suite — so it's free, fast, and deterministic.

---

## Step 7 — Google Calendar (OAuth)

Only after everything above is green. **Only `calendar_store.py` changes.** If
`agent.py` needs edits, the abstraction in Step 1 was wrong.

---

## Step 8 — Learned scheduling profile

Motivation: `WORK_START_HOUR = 9` is a guess. Which slot is *good* is subjective,
so derive it from a couple weeks of the user's actual calendar (or a manually
written `profile.json`).

**Architecture.** Personalization is policy, not storage, so it does **not** go in
`calendar_store.py` — that file gets swapped wholesale for Google in Step 7 and
would take the profile logic with it.

```
agent.py
  ├── scheduling.py        ranks/filters slots using the profile
  │     └── profile.json      the learned artifact
  └── calendar_store.py    raw gaps over a wide floor window (07:00–22:00), no opinions
```

`find_free_slots` stays mechanical. `scheduling.py` narrows and orders. This keeps
the Step 7 swap clean and makes ranking testable offline against a fixed profile
with no calendar and no network.

**Two tiers**, extending "logic in Python, judgment in the model":

*Tier 1 — Python computes statistics.* Deterministic, testable, free.
- Working bounds from **percentiles** of busy-minute histogram (5th/95th), not
  min/max — one 6am airport run destroys min/max.
- **Per-weekday** bounds. Cheapest big win; Friday ends earlier than Tuesday.
- Observed **buffer** = median gap between consecutive meetings.
- Meeting **density by hour** → the ranking signal.

*Tier 2 — the model interprets.* Two narrow roles only:
- Classify distinct event titles once at build time (`meeting` / `focus` /
  `personal` / `commute` / `recurring-admin`), cached into `profile.json`.
- Tie-break among 5–10 candidate slots Python already validated.

Never ask the model "what are their working hours?" — non-deterministic, costs
tokens every run, and yields a number you can't unit-test.

**The inference trap.** Absence of events ≠ preference for free time. An empty
Thursday afternoon may be protected focus time or merely unbooked; the calendar
cannot distinguish them. Weight **self-authored blocks** (no attendees — "deep
work", "gym") far higher than meetings: meetings show when the user is
*available*, self-created blocks show what they *want*.

**The artifact.** Plain JSON, regenerated explicitly via `--learn` (never silently
per-run), carrying its own provenance so ranking code can decide whether to trust
it, and hand-editable — which doubles as the manual-upload path.

```json
{
  "version": 1, "generated_at": "...", "sample_window_days": 14,
  "sample_event_count": 63,
  "work_hours": {"mon": {"start": "09:00", "end": "17:30"},
                 "fri": {"start": "09:00", "end": "15:00"}},
  "min_buffer_minutes": 15,
  "focus_preferred_hours": [9, 10, 11],
  "title_labels": {"Standup": "recurring-admin"}
}
```

**Cold start** — thresholds decided up front. Under ~20 events → defaults
entirely. A weekday with under ~3 sample days → global bounds for that day.
Learned bounds always intersected with a sanity floor so a bad inference can't
produce "03:00–04:00". The profile is a *nudge over* defaults, never a
replacement.

**Cautions.** Real titles are sensitive (clients, medical, interviews) — send
aggregates and reviewed distinct titles, never raw event dumps with attendees or
descriptions. And two weeks is 10 working days: enough for hour-of-day bounds and
buffers, not enough for anything weekly-cyclical (monthly all-hands, biweekly
1:1s). Don't over-model what the data can't support.

**Sub-order:** ranking layer over a *hand-written* profile first (pure Python, no
model, and where most of the value is) → then `--learn` Tier 1 stats → then the
model's classification pass.

---

## Definition of done

- Handles the three example requests without manual intervention.
- Recovers from a malformed tool call rather than crashing.
- Test suite runs offline.
- README documents the architecture, the failure modes hit during development,
  and how they were fixed.

## Known hard parts

- Timezones and daylight-saving boundaries.
- Respecting working hours and existing-event conflicts in `find_free_slots`.
- Agent looping without making progress.
- Context growth on long sessions.
- Deciding what the agent may do autonomously versus what needs approval.
