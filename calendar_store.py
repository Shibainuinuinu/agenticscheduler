
from datetime import datetime, timedelta, time
import json
import uuid
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

CALENDAR_ID="5ca24ad20cdd8874bb400f893d20993a1f5ae7c8e77b4466f3c0f19510d8b22d@group.calendar.google.com"
EVENTS_FILE = Path(__file__).parent / "events.json"
TOKEN_FILE = Path(__file__).parent / "token.json"
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
# Read and write events only -- nothing else in the Google account.
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
WORK_START_HOUR = 9
WORK_END_HOUR = 17

# An event as stored in events.json: id, title, start, end — all ISO strings.
Event = dict[str, str]
# A candidate gap: only start and end. No id, no title — it doesn't exist yet.
Slot = dict[str, str]


def _get_service():
    """A logged-in Google Calendar client.

    First run opens a browser to log in and saves the token to token.json.
    Later runs reuse the token, refreshing it silently when it expires.
    """
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def list_events(start_date: str, end_date: str) -> list[Event]:
    """events overlapping [start_date, end_date) — upper bound exclusive"""
    window_start = datetime.fromisoformat(start_date)
    window_end = datetime.fromisoformat(end_date)

    with open(EVENTS_FILE, 'r', encoding='utf-8') as f:
        events = json.load(f)

    return [
        event for event in events
        if datetime.fromisoformat(event['end']) > window_start
        and datetime.fromisoformat(event['start']) < window_end
    ]

def find_free_slots(
    start_date: str, end_date: str, duration_minutes: int
) -> list[Slot]:
    """candidate gaps long enough to fit

    end_date is *inclusive* of the whole final day, unlike list_events, whose
    upper bound is exclusive.
    """
    res: list[Slot] = []

    range_start = datetime.fromisoformat(start_date)
    range_end = datetime.fromisoformat(end_date)
    # list_events takes an exclusive upper bound, so hand it midnight after
    # the final day to cover that day's events.
    window_end = datetime.combine(range_end.date() + timedelta(days=1), time.min)

    filtered_events = list_events(start_date, window_end.isoformat())
    filtered_events.sort(key=lambda e: datetime.fromisoformat(e['start']))

    first_day_start = range_start.replace(
        hour=WORK_START_HOUR, minute=0, second=0, microsecond=0
    )

    for day in range((range_end.date() - range_start.date()).days + 1):
        day_start = first_day_start + timedelta(days=day)
        day_end = day_start + timedelta(hours=WORK_END_HOUR - WORK_START_HOUR)
        day_events = [
            event for event in filtered_events
            if datetime.fromisoformat(event['end']) > day_start
            and datetime.fromisoformat(event['start']) < day_end
        ]

        # No special case for an empty day: the loop below runs zero times,
        # cursor stays at day_start, and the trailing check emits the whole window.
        cursor = day_start
        for event in day_events:
            # Clamp into the working window so the cursor never leaves it
            event_start = max(datetime.fromisoformat(event['start']), day_start)
            event_end = min(datetime.fromisoformat(event['end']), day_end)

            # Check for free slot before the current event
            if (event_start - cursor).total_seconds() / 60 >= duration_minutes:
                res.append({
                    "start": cursor.isoformat(),
                    "end": event_start.isoformat()
                })

            # Move the cursor to the end of the current event
            cursor = max(cursor, event_end)

        # Check for free slot after the last event of the day
        if (day_end - cursor).total_seconds() / 60 >= duration_minutes:
            res.append({
                "start": cursor.isoformat(),
                "end": day_end.isoformat()
            })


    return res


def create_event(title: str, start: str, end: str) -> dict[str, Event]:
    """the new event, with a fresh id"""
    unique_id = str(uuid.uuid4())
    event: Event = {
        "id": unique_id,
        "title": title,
        "start": start,
        "end": end
    }

    with open(EVENTS_FILE, 'r+', encoding='utf-8') as f:
        events = json.load(f)
        for existing in events:
            if existing['title'] == title and existing['start'] == start and existing['end'] == end:
                raise ValueError(f"Duplicate event: {existing}")
        
        events.append(event)
        f.seek(0)
        json.dump(events, f, indent=2)
        f.truncate()

        return {"created": event}


def delete_event(event_id: str) -> dict[str, str]:
    """confirmation, or raises if not found"""
    with open(EVENTS_FILE, 'r+', encoding='utf-8') as f:
        events = json.load(f)
        updated_events = [event for event in events if event['id'] != event_id]
        if len(updated_events) == len(events):
            raise ValueError(f"Event with id {event_id} not found.")
        f.seek(0)
        json.dump(updated_events, f, indent=2)
        f.truncate()

        return {"deleted": event_id}

