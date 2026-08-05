"""CLI scheduling agent: the loop, the tool schemas, and the dispatch.

Run:  .venv/Scripts/python.exe agent.py "what's on my Wednesday?"
"""

import json
import sys

from google import genai

import calendar_store

MODEL = "gemini-3.6-flash"
MAX_STEPS = 10

SYSTEM_INSTRUCTION = """\
You are a scheduling assistant. Today is 2026-08-04.

Never compute or invent timestamps yourself. To find free time, call
find_free_slots and choose from the slots it returns.
"""

# The model sees ONLY these three things per tool -- name, description, and the
# JSON Schema of the parameters. It never sees the Python. The description is
# what makes the model call it correctly, so it is real code, not a comment.
#
# One worked example below; add the other three in Step 3.
TOOLS = [
    {
        "type": "function",
        "name": "list_events",
        "description": (
            "List calendar events overlapping a date range. "
            "Dates are ISO 8601, e.g. 2026-08-05 or 2026-08-05T14:00. "
            "The end bound is exclusive."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "Start of the range, ISO 8601.",
                },
                "end_date": {
                    "type": "string",
                    "description": "End of the range, ISO 8601, exclusive.",
                },
            },
            "required": ["start_date", "end_date"],
        },
    },
    # TODO Step 3: find_free_slots (start_date, end_date, duration_minutes)
    #              note its end_date is INCLUSIVE of the last day -- say so here
    # TODO Step 3: create_event (title, start, end)
    # TODO Step 3: delete_event (event_id)
]

# Maps the tool name the model uses to the Python function that runs it.
# TODO: fill in as you add tools above.
DISPATCH = {
    "list_events": calendar_store.list_events,
}


def execute(step) -> dict:
    """Run one function_call step and build the function_result to send back.

    `step` has .name, .arguments (a dict), and .id.

    The returned dict must be shaped:
        {"type": "function_result",
         "name": <the tool name>,
         "call_id": <step.id>,          # must match, or the model loses track
         "result": [{"type": "text", "text": json.dumps(<your return value>)}]}

    TODO:
      1. look up step.name in DISPATCH
      2. call it with **step.arguments
      3. wrap the return value in the shape above

    Step 4 wraps this in try/except and returns the error text as the result
    instead of crashing. Step 5 adds the y/n confirmation for writes. Leave
    both out for now.
    """
    raise NotImplementedError


def run(user_request: str) -> str:
    """Drive the model until it stops asking for tools; return its final text.

    TODO:
      1. first call: client.interactions.create(
             model=MODEL, input=user_request, tools=TOOLS,
             system_instruction=SYSTEM_INSTRUCTION)
      2. loop up to MAX_STEPS:
           - pull the function_call steps out of interaction.steps
           - if there are none, the model answered in words -> return the text
           - otherwise execute() each one; EVERY call needs exactly ONE result
           - send the results back as the next `input`, passing
             previous_interaction_id=interaction.id
      3. if the loop runs out, say so rather than returning nothing

    Note: tools and system_instruction are interaction-scoped -- you must pass
    them on EVERY call, not just the first. previous_interaction_id carries the
    history, not the configuration.
    """
    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    raise NotImplementedError


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f'usage: python {sys.argv[0]} "your request"')
        sys.exit(1)

    print(run(" ".join(sys.argv[1:])))
