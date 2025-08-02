import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import pytz
from rapidfuzz import fuzz
from typing import List, Dict

CALENDAR_ID='ae74fa4fda8818b1fac026895d5eb544540b0799567bd8e16ca771250f6bc1bf@group.calendar.google.com'
TASKLIST_ID='MjFUS0VlSGtRRldRalhueg'


SCOPES = ["https://www.googleapis.com/auth/calendar",'https://www.googleapis.com/auth/tasks']

def get_creds():
  creds = None
  # The file token.json stores the user's access and refresh tokens, and is
  # created automatically when the authorization flow completes for the first
  # time.
  if os.path.exists("/Users/akshaythammana/Ai_Calendar/token.json"):
    creds = Credentials.from_authorized_user_file("/Users/akshaythammana/Ai_Calendar/token.json", SCOPES)
  # If there are no (valid) credentials available, let the user log in.
  if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      flow = InstalledAppFlow.from_client_secrets_file(
          "/Users/akshaythammana/Ai_Calendar/creds.json", SCOPES
      )
      creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open("/Users/akshaythammana/Ai_Calendar/token.json", "w") as token:
      token.write(creds.to_json())

  return creds
  
def convert_ist_to_api_timestamp(date_string: str) -> str:
    """
    Converts a date and time string from IST to an RFC 3339 formatted UTC string.

    This is the required format for the Google Tasks API. It handles the timezone
    conversion to ensure the due date is set correctly.

    Args:
        date_string (str): The date and time as a string in IST.
                           Example: '2025-08-10 21:00:00' in format '%Y-%m-%d %H:%M:%S'.

    Returns:
        str: An RFC 3339 formatted UTC timestamp string.
             Example: '2025-08-10T15:30:00+00:00'
    """
    try:
        # Define the IST timezone.
        ist_timezone = pytz.timezone('Asia/Kolkata')
        
        # Parse the input string into a naive datetime object.
        desired_ist_time = datetime.strptime(date_string,'%Y-%m-%d %H:%M:%S' )
        
        # Localize the naive datetime object to the IST timezone.
        localized_ist_time = ist_timezone.localize(desired_ist_time)
        
        # Convert the IST timezone-aware datetime object to UTC.
        utc_time = localized_ist_time.astimezone(pytz.utc)
        
        # Format the UTC time as an RFC 3339 string.
        # isoformat() handles the formatting, including the timezone offset.
        return utc_time
    except Exception as e:
        print(f"Error converting timestamp: {e}")
        raise

def get_events(start_datetime_str: str = None, end_datetime_str: str = None):
    """
    Retrieves all Google Calendar events between the specified start and end datetimes.

    Args:
        start_datetime_str (str, optional): Start datetime in '%Y-%m-%d %H:%M:%S' (IST). Defaults to today.
        end_datetime_str (str, optional): End datetime in '%Y-%m-%d %H:%M:%S' (IST). Defaults to 7 days from start.

    Returns:
        list: List of event resource dicts.
    """
    # make calendar id gobal variable
    creds = get_creds()


    # Handle default dates (now to 7 days later)
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)

    if not start_datetime_str:
        start_datetime= tz.localize(datetime(now.year, now.month, now.day))
    else:
        start_datetime = convert_ist_to_api_timestamp(start_datetime_str)
    
    if not end_datetime_str:
        end_datetime = start_datetime + timedelta(days=7)
    else:
        end_datetime = convert_ist_to_api_timestamp(end_datetime_str)

    service = build('calendar', 'v3', credentials=creds)

    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start_datetime.isoformat(),
        timeMax=end_datetime.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    return events_result.get('items', [])


def create_event(
    summary: str,
    start_datetime_str: str,
    end_datetime_str: str,
    description: str = "",
    location: str = "",
    attendees: str = None,
    reminders: str = None,
):
    """
    Creates a new event in the configured Google Calendar.

    Args:
        summary (str): Event title.
        start_datetime_str (str): Start datetime in '%Y-%m-%d %H:%M:%S' (IST).
        end_datetime_str (str): End datetime in '%Y-%m-%d %H:%M:%S' (IST).
        description (str, optional): Event description.
        location (str, optional): Event location.
        attendees (list, optional): List of attendee emails.
        reminders (dict, optional): Reminder configuration.

    Returns:
        dict: The created event resource.
    """

    # Step 1: Handle Credentials
    creds = get_creds()
    
    # Handle default dates (now to 7 days later)
    tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(tz)

    if not start_datetime_str:
        start_datetime= tz.localize(datetime(now.year, now.month, now.day))
    else:
        start_datetime = convert_ist_to_api_timestamp(start_datetime_str)
    
    if not end_datetime_str:
        end_datetime = start_datetime + timedelta(days=7)
    else:
        end_datetime = convert_ist_to_api_timestamp(end_datetime_str)
    
    
    # Step 2: Build the event data
    service = build("calendar", "v3", credentials=creds)

    event_body = {
        "summary": summary,
        "location": location,
        "description": description,
        "start": {
            "dateTime": start_datetime.isoformat(),
            "timeZone": "Asia/Kolkata",  # Adjust as needed
        },
        "end": {
            "dateTime": end_datetime.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "reminders": reminders or {"useDefault": True},
    }

    if attendees:
        event_body["attendees"] = [{"email": email} for email in attendees]

    # Step 3: Create the event
    event = service.events().insert(calendarId=CALENDAR_ID, body=event_body).execute()
    return event


def get_event_by_name_and_timefarame(name: str, start_datetime_str: str, end_datetime_str: str, threshold: int = 65, top_k: int = 5) -> List[Dict]:
    """
    Performs fuzzy search for events by name within a time window.

    Args:
        name (str): Search query for event summary.
        start_datetime_str (str): Start datetime in '%Y-%m-%d %H:%M:%S' (IST).
        end_datetime_str (str): End datetime in '%Y-%m-%d %H:%M:%S' (IST).
        threshold (int, optional): Minimum fuzzy match score (0–100).
        top_k (int, optional): Maximum number of results to return.

    Returns:
        List[dict]: List of matched event resource dicts.
    """

    events = get_events(start_datetime_str,end_datetime_str)
    if not events:
        print('No events found')
        return
    matches = []

    for event in events:
        title = event.get("summary", "")
        score = fuzz.partial_ratio(name.lower(), title.lower())  # partial = "contains-like"
        if score >= threshold:
            matches.append((score, event))

    # Sort by match score descending
    matches.sort(reverse=True, key=lambda x: x[0])
    return [event for score, event in matches[:top_k]]

def edit_event_by_id(event_id, updated_fields):
    """
    Updates an existing Google Calendar event by ID.

    Args:
        event_id (str): The event's unique identifier.
        updated_fields (dict): Fields to update (e.g., {'summary': 'New Title'}).

    Returns:
        dict: The updated event resource, or None if update fails.
    """
    creds = get_creds()
    service = build('calendar', 'v3', credentials=creds)
    # try:
        # Get the existing event
    event = service.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()

    # Update event with new fields
    event.update(updated_fields)

    # Push the update
    updated_event = service.events().update(
        calendarId=CALENDAR_ID,
        eventId=event_id,
        body=event
    ).execute()

    return updated_event

def list_task_lists():
    """
    Lists all available Google Task lists for the authenticated user.

    Prints each task list's title and ID.
    """
    creds = get_creds()
    service = build('tasks', 'v1', credentials=creds)

    results = service.tasklists().list(maxResults=10).execute()
    tasklists = results.get('items', [])
    for tl in tasklists:
        print(f"{tl['title']} (ID: {tl['id']})")

def list_tasks():
    """
    Lists all tasks in the default task list.

    Prints each task's title,status and ID.
    """
    creds = get_creds()
    service = build('tasks', 'v1', credentials=creds)
    

    results = service.tasks().list(tasklist=TASKLIST_ID).execute()
    tasks = results.get('items', [])
    for task in tasks:
        print(f"{task['title']} - Status: {task['status']} - ID:{tasks['id']}")

def create_task(title, notes=None, due=None):
    """
    Creates a new task in the default Google Task list.

    Args:
        title (str): Task title.
        notes (str, optional): Task notes.
        due (str, optional): Due date in RFC 3339 format IST.

    Returns:
        dict: The created task resource.
    """
    creds = get_creds()
    service = build('tasks', 'v1', credentials=creds)

    task = {
        'title': title,
        'notes': notes,
        'due': due  # ISO 8601: '2025-08-01T17:00:00.000Z'
    }
    return service.tasks().insert(tasklist=TASKLIST_ID, body=task).execute()

def edit_task_from_json(task_id, update_payload: dict):
    """
    Updates a Google Task using a dictionary of fields.

    Args:
        service: Google Tasks API service object.
        task_id (str): ID of the task to update.
        update_payload (dict): Fields to update (e.g., {'title': 'New Title'}).

    Returns:
        dict: The updated task resource, or None if update fails.
    """
    creds = get_creds()
    service = build('tasks', 'v1', credentials=creds)


    try:
        # Get the current task
        task = service.tasks().get(tasklist=TASKLIST_ID, task=task_id).execute()

        # Update with new fields
        task.update(update_payload)

        # Push the update
        updated_task = service.tasks().update(tasklist=TASKLIST_ID, task=task_id, body=task).execute()
        return updated_task

    except Exception as e:
        print("Error updating task:", e)
        return None
    
def fuzzy_search_tasks(name='', top_n=5,score_cutoff=50):
    """
    Performs fuzzy search for tasks by title.

    Args:
        name (str): Search query for task title.
        top_n (int, optional): Maximum number of results to return.
        score_cutoff (int, optional): Minimum fuzzy match score (0-100).

    Returns:
        A list of matched task dicts (with title and id) sorted by similarity.
    """
    creds = get_creds()
    service = build('tasks', 'v1', credentials=creds)

    try:
        result = service.tasks().list(tasklist=TASKLIST_ID).execute()
        tasks = result.get('items', [])

        if not tasks:
            return []

        matches = []

        for task in tasks:
            title = task.get("title", "")
            score = fuzz.partial_ratio(name.lower(), title.lower())  # partial = "contains-like"
            if score >= score_cutoff:
                matches.append((score, task))

        # Sort by match score descending
        matches.sort(reverse=True, key=lambda x: x[0])
        return [event for score, event in matches[:top_n]]

    except Exception as e:
        print("Error in fuzzy_search_tasks:", e)
        return []

