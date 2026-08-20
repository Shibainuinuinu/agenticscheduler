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
                    "description": "End of the range, ISO 8601, exclusive.",
                },
                "duration_minutes": {
                    "type": "integer",
                    "description": (
                        "Minimum duration of the free slot, in minutes."
                    ),
                },
            },
            "required": ["start_date", "end_date"],
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
    return {
        "type": "function_result",
        "name": step.name,
        "call_id": step.id,
        "result": [{"type": "text", "text": json.dumps(DISPATCH[step.name](**step.arguments))}]
    }


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
