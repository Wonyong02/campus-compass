import json
from datetime import datetime

from strands import Agent

EVENTS_FILE = "my_agent/deanza_events.json"

PRIORITY_SYSTEM_PROMPT = """
You are a campus event prioritization assistant. You will be given:
- today's date
- a student profile (year, major, interests)
- a list of real campus events (title, date, time, location, description)

For each event, decide how important it is for THIS student, based on:
- how soon the event happens relative to today's date
- how well the event's title/description relates to the student's major and interests
- whether the event type suits the student's year (e.g. transfer or application
  workshops matter more to students close to transferring; general deadlines
  matter to everyone)

Respond ONLY with a JSON array (no prose, no markdown fences). Each item must
look exactly like:
{
  "id": <event id, integer>,
  "tier": "high" | "medium" | "low",
  "reason": "<one short sentence, under 15 words>"
}

Guidance:
- "high": within the next few days AND clearly relevant to this student.
- "medium": relevant but not urgent, or soon but only loosely relevant.
- "low": neither urgent nor clearly relevant to this student.

Order the array from most to least important. If an event's date is missing
or unclear, treat it as not urgent.
"""


def build_agent() -> Agent:
    return Agent(system_prompt=PRIORITY_SYSTEM_PROMPT)


def load_events(path: str = EVENTS_FILE) -> list[dict]:
    with open(path) as f:
        raw_events = json.load(f)

    events = []
    for i, ev in enumerate(raw_events):
        if not ev.get("title"):
            continue  # skip anything the scraper couldn't parse cleanly
        events.append({
            "id": i,
            "title": ev["title"],
            "date": ev.get("date"),
            "time": ev.get("time"),
            "location": ev.get("location"),
            "description": (ev.get("description") or "")[:300],  # keep the prompt lean
        })
    return events


def prioritize_events(student_profile: dict, events: list[dict]) -> list[dict]:
    agent = build_agent()
    payload = {
        "today": datetime.now().strftime("%Y-%m-%d"),
        "student_profile": student_profile,
        "events": events,
    }
    prompt = f"Here is the data:\n{json.dumps(payload, indent=2)}"

    response = agent(prompt)
    raw_text = str(response)

    start = raw_text.find("[")
    end = raw_text.rfind("]") + 1
    return json.loads(raw_text[start:end])


if __name__ == "__main__":
    student_profile = {
        "year": "sophomore",
        "major": "Computer Science",
        "interests": ["career", "academic"],
    }

    events = load_events()
    print(f"Loaded {len(events)} real events from {EVENTS_FILE}\n")

    ranked = prioritize_events(student_profile, events)

    print("=== Prioritized Real Events ===")
    for item in ranked:
        event = next(e for e in events if e["id"] == item["id"])
        print(f"[{item['tier'].upper():6}] {event['title']} ({event['date']})  —  {item['reason']}")
