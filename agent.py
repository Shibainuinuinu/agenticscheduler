"""CLI scheduling agent: the loop, the tool schemas, and the dispatch.

Run:  .venv/Scripts/python.exe agent.py "what's on my Wednesday?"
"""

import json
import sys

from google import genai
from dotenv import load_dotenv

import calendar_store

load_dotenv()
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
    {
        "type": "function",
        "name": "find_free_slots",
        "description": (
            "Find free time slots within a date range. "
            "Dates are ISO 8601, e.g. 2026-08-05 or 2026-08-05T14:00. "
            "The end bound is inclusive."
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
                    "description": "End of the range, ISO 8601, inclusive.",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": (
                        "Minimum duration of the free slot, in minutes."
                    ),
                },
            },
            "required": ["start_date", "end_date", "duration_minutes"],
        },
    },
    {
        "type": "function",
        "name": "create_event",
        "description": (
            "Create a new calendar event. "
            "Dates are ISO 8601, e.g. 2026-08-05 or 2026-08-05T14:00. "
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Title of the event.",
                },
                "start": {
                    "type": "string",
                    "description": "Start of the event, ISO 8601.",
                },
                "end": {
                    "type": "string",
                    "description": "End of the event, ISO 8601.",
                },
            },
            "required": ["title", "start", "end"],
        },
    },
    {
        "type": "function",
        "name": "delete_event",
        "description": (
            "Delete a calendar event. "
            "The event is identified by its ID."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "ID of the event to delete.",
                },
            },
            "required": ["event_id"],
        },
    },
]

# Maps the tool name the model uses to the Python function that runs it.
DISPATCH = {
    "list_events": calendar_store.list_events,
    "find_free_slots": calendar_store.find_free_slots,
    "create_event": calendar_store.create_event,
    "delete_event": calendar_store.delete_event 
}

# Tools that change the calendar. These need a y/n from the user first.
WRITE_TOOLS = {"create_event", "delete_event"}


def execute(step) -> dict:
    """Run one function_call step and build the function_result to send back.

    `step` has .name, .arguments (a dict), and .id.

    The returned dict must be shaped:
        {"type": "function_result",
         "name": <the tool name>,
         "call_id": <step.id>,          # must match, or the model loses track
         "result": [{"type": "text", "text": json.dumps(<your return value>)}]}


    Errors are returned as the result instead of crashing, so the model can
    self-correct. Write tools need a y/n from the user before they run.
    """
    print(f"Executing {step.name} with arguments {step.arguments}", file=sys.stderr)

    if step.name in WRITE_TOOLS:
        answer = input(f"Allow {step.name} {step.arguments}? [y/n] ")
        if answer.strip().lower() != "y":
            # Declining is a normal result, not an error: an error would
            # invite the model to retry with different arguments.
            return {
                "type": "function_result",
                "name": step.name,
                "call_id": step.id,
                "result": [{"type": "text", "text": json.dumps(
                    {"declined": "The user declined. Nothing was changed."}
                )}],
            }

    try:
        result = DISPATCH[step.name](**step.arguments)
        text = json.dumps(result)
        print(f"Result: {text}", file=sys.stderr)
    except Exception as e:
        text = json.dumps({"error": str(e)})
        print(f"Error executing {step.name}: {e}", file=sys.stderr)

    return {
        "type": "function_result",
        "name": step.name,
        "call_id": step.id,
        "result": [{"type": "text", "text": text}]
    }

def run(user_request: str) -> str:
    """Drive the model until it stops asking for tools; return its final text.

    Note: tools and system_instruction are interaction-scoped -- you must pass
    them on EVERY call, not just the first. previous_interaction_id carries the
    history, not the configuration.
    """
    client = genai.Client()  # reads GEMINI_API_KEY from the environment
    interaction = client.interactions.create(
        model=MODEL,
        input=user_request,
        tools=TOOLS,
        system_instruction=SYSTEM_INSTRUCTION
    )

    for _ in range(MAX_STEPS):
        function_calls = [s for s in interaction.steps if s.type == "function_call"]
        if not function_calls:
            return interaction.output_text

        results = [execute(s) for s in function_calls]
        interaction = client.interactions.create(
            model=MODEL,
            input=results,
            tools=TOOLS,
            system_instruction=SYSTEM_INSTRUCTION,
            previous_interaction_id=interaction.id
        )
        
    return f"Ran out of steps ({MAX_STEPS}) without a final answer."
        


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f'usage: python {sys.argv[0]} "your request"')
        sys.exit(1)

    print(run(" ".join(sys.argv[1:])))
