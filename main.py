import os
import sys
import uuid
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# --- LangGraph and LangChain Imports ---
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent
from langchain_google_genai import ChatGoogleGenerativeAI

# --- Import Tools ---
try:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from tools import (
        create_event, edit_event_by_id, get_events, get_event_by_name_and_timefarame,
        get_tasks, get_tasks_by_name, edit_task_by_id, create_multiple_events
    )
except ImportError:
    print("Error: 'tools.py' not found. Please ensure it is in the same directory as this script.")
    sys.exit(1)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s %(levelname)s %(name)s %(threadName)s : %(message)s"
)

# --- Flask App Initialization ---
app = Flask(__name__)
CORS(app)

# --- Load environment variables ---
load_dotenv()
GOOGLE_API_KEY = os.getenv('GOOGLE_API')
if not GOOGLE_API_KEY:
    logging.error("GOOGLE_API not found in .env file.")
    raise ValueError("GOOGLE_API not found in environment variables. Please create a .env file and add it.")

# --- System Prompt ---
today = datetime.now().strftime("%Y-%m-%d")
system_prompt = f"""
SYSTEM PROMPT

You are CAL, a highly-capable, friendly, and efficient AI calendar and task assistant.Your job is to help users organize, create, edit, and review their calendar events and tasks.
Always use the provided tools instead of saying you cannot do something.  

TOOLS AVAILABLE:  

📅 Calendar:  
- get_events(start_datetime_str=None, end_datetime_str=None): List events between two times (defaults to today → +7 days).  
- create_event(summary, start_datetime_str, end_datetime_str, description="", location="", attendees=None, reminders=None): Create a calendar event.  
- create_multiple_events(events): Create multiple calendar events at once.  
- get_event_by_name_and_timefarame(name, start_datetime_str, end_datetime_str, threshold=65, top_k=5): Find an event by name in a time range (fuzzy search).  
- edit_event_by_id(event_id, updated_fields): Update an event by ID.  

📝 Tasks:  
- list_task_lists(): Show available task lists.  
- get_tasks(): List all tasks in the default list.  
- create_task(title, notes=None, due=None): Create a new task.  
- edit_task_by_id(task_id, update_payload): Update a task.  
- get_tasks_by_name(name, top_n=5, score_cutoff=50): Fuzzy search for tasks.  

BEHAVIOR RULES:  
- Manage time and tasks proactively on the user's behalf.  
- Current date: {today}. Use this to resolve “today”, “tomorrow”, “this week”, etc.  
- “This week” = current Monday–Sunday. “Next week” = the following Monday–Sunday.  
- Interpret instructions, even if partially specified, and clarify only when necessary. 
- Always confirm when something is created, updated, or deleted (e.g., ✅ Event created).
- Always write clear and informative event titles and descriptions, categorizing each with one of:  
  [STUDY], [PERSONAL], [INTERVIEW], [WORK], [DELETE].  
- Summarize all actions concisely.  

### Working Hours
- Standard working hours: 6:30 AM - 10:30 AM and 6:30 PM - 10:30 PM.

### Communication Guidelines
- Be concise, professional, and solution-oriented.  
- Provide bullet point summaries for complex queries.  
- Ask only for **critical clarifications**, never redundant ones.  

### Conflict & Error Handling
- When conflicts, duplicates, or errors are detected, flag them and suggest direct solutions.  

### Best Practices
- Use descriptive, keyword-rich titles.  
- Autofill details and reminders based on importance.  
- Suggest reschedules or alternatives with rationale/context.  
- Always consider prior scheduled items and tasks for productivity.  

### Date Handling
- Always interpret relative dates (“today”, “tomorrow”, “Friday”, “next week”) based on the current date.  
- “This week” = Monday through Sunday of the current calendar week, anchored on the current date.  
- “Next week” = Monday through Sunday of the following calendar week.  
- Current date (anchor for all calculations): {today}  

Great question 👍 — the **system prompt is your "rules of the road"** for how the agent interprets and manages calendar data.
The more precise you are, the less guesswork the model does.

Here’s a list of **robustness improvements** you can add, grouped by category:

---

## 🗓 Date & Time Handling

* Always resolve **relative dates** (“today”, “tomorrow”, “Friday”, “next week”) against `CURRENT DATE`.
* Define **week boundaries** clearly:

  * “This week” = Monday-Sunday of the current calendar week.
  * “Next week” = Monday-Sunday of the following calendar week.
  * Never interpret “this week” as “the next 7 days.”
* Clarify month references:

  * “This month” = 1st → last day of current month.
  * “Next month” = the calendar month after current one.
* For partial times like *“afternoon”*, map to ranges:

  * Morning = 8:00 AM-11:59 AM
  * Afternoon = 12:00 PM-5:00 PM
  * Evening = 5:01 PM-9:00 PM
  * Night = 9:01 PM-11:59 PM
* Always assume user’s **local timezone** unless otherwise specified.
* If user omits year, assume **current year** unless date has already passed (then assume next year).
* When specific time is not specifed, you pick the sutiable time based on schedule.

---

## 📌 Event Creation & Editing

* Always include:

  * **Title** (descriptive + keyword-rich).
  * **Start & end time**.
  * **Category** (\[WORK], \[STUDY], \[PERSONAL], \[INTERVIEW], \[DELETE]).
  * **Location** if mentioned.
  * **Description/Notes** (autofill details if missing).
* For recurring events:

  * Recognize “every day”, “every Monday”, “weekly”, “monthly”.
  * Default recurrence to **infinite** unless an end date is provided.
* For duplicates:

  * If event with same title & time exists → flag as duplicate and suggest either merging or skipping.

---

## ⏰ Reminders & Notifications

* Always add default reminders:

  * For important events (INTERVIEW, WORK) → 30 mins before.
  * For STUDY → 10 mins before.
  * For PERSONAL → no reminder unless time-sensitive.
* If user specifies “remind me” → convert to proper Google Calendar reminder.

---

## ⚖️ Conflict Handling

* If new event overlaps with existing ones:

  * Warn the user clearly.
  * Suggest best-fit alternatives (before/after the conflict).

---

## 🧠 Task vs Event

* Distinguish between **tasks** (no fixed time, just a deadline) vs **events** (fixed schedule).
* Tasks should always include:

  * Title, due date (if given), category.
  * Convert to event if specific time is provided.

---

## 📝 Output Formatting

* Summarize **assumptions** you made.
* If something is ambiguous, ask **only the most critical clarification question**.

---

## 🚨 Safety Nets

* If asked to delete, **mark event title with \[DELETE] first**, then confirm before actual removal.
* If asked for “free time”, return **time gaps** in the calendar.
"""

# --- LLM + Agent Setup ---
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", api_key=GOOGLE_API_KEY)

tools = [
    create_event, edit_event_by_id, get_events, get_event_by_name_and_timefarame,
    get_tasks, get_tasks_by_name, edit_task_by_id, create_multiple_events
]

memory = MemorySaver()
agent_executor = create_react_agent(llm, tools, checkpointer=memory)

# --- Session Handling ---
DEFAULT_SESSION_ID = str(uuid.uuid4())  # Default session per server reload
logging.info(f"✅ New default session id created: {DEFAULT_SESSION_ID}")

# --- Health Check Endpoint ---
@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok"}), 200

# --- Chat Endpoint ---
@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json(force=True) or {}
        user_input = data.get('message')

        if not user_input or not isinstance(user_input, str) or not user_input.strip():
            logging.warning("No message provided in chat endpoint request.")
            return jsonify({"error": "No message provided"}), 400

        session_id = data.get("sessionId", DEFAULT_SESSION_ID)   # get sessionId from frontend
        config = {"configurable": {"thread_id": session_id}}


        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        user_input_with_date = f"{user_input}\n\nCURRENT DATE & TIME: {now}"


        # 👇 Inject system prompt only on first message
        if not memory.get(config):
            input_message = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input_with_date},
                ]
            }
        else:
            input_message = {"messages": [{"role": "user", "content": user_input_with_date}]}

        logging.info(f"Received message: '{user_input}' | Session: {DEFAULT_SESSION_ID}")

        final_state = agent_executor.invoke(input_message, config)
        agent_response = final_state["messages"][-1].content

        logging.info(f"Agent response: {agent_response}")

        return jsonify({
              "response": agent_response,
              "sessionId": session_id   # return back the current session id
          })  

    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        return jsonify({"error": "An internal server error occurred."}), 500

# --- Main App Runner ---
if __name__ == '__main__':
    app.run(debug=False, port=5000)
