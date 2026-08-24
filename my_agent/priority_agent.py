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


def _extract_json_array(text: str) -> str:
    """Pulls the first balanced top-level [...] block out of the agent's raw
    response, ignoring brackets that appear inside quoted strings (e.g. a
    "reason" like "See [1] for details" won't throw off the count).

    The old version just did text.find("[") / text.rfind("]") -- a naive
    find/rfind pair. That mostly worked when the agent behaved, but breaks
    in a few real ways: an empty/no-bracket response slices to "" and
    json.loads("") raises an opaque "Expecting value" error with no hint of
    what actually came back; a response with any stray "]" after the array
    (e.g. the model added a trailing note) gets silently included in the
    slice; and there's no useful error message either way to debug from.

    Raises ValueError with a snippet of the actual response on failure, so a
    parsing problem is diagnosable from the /api/rerank 502 body alone
    instead of just "Expecting value: line 1 column 1 (char 0)".
    """
    start = text.find("[")
    if start == -1:
        raise ValueError(f"agent response contained no JSON array at all -- raw response: {text[:500]!r}")

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]

    raise ValueError(f"agent response had an unclosed JSON array (unbalanced brackets) -- raw response: {text[:500]!r}")


def build_agent_input(raw_events: list[dict]) -> tuple[list[dict], dict[int, dict]]:
    """Turns raw scraped(+geocoded) events into the trimmed shape the agent
    expects (id, title, date, time, location, description capped at 300
    chars), skipping anything the scraper couldn't parse a title for.

    Returns (agent_input, id_lookup): agent_input is what goes in the prompt,
    id_lookup maps each assigned id back to the *original* event dict so a
    caller can merge the agent's tier/reason onto the full record afterward.

    This used to be copy-pasted in three places (here, pipeline.py, and
    app.py) -- now pipeline.py and app.py both call this instead of keeping
    their own copy of the skip/trim logic in sync by hand.
    """
    agent_input = []
    id_lookup = {}
    for i, ev in enumerate(raw_events):
        if not ev.get("title"):
            continue  # skip anything the scraper couldn't parse cleanly
        agent_input.append({
            "id": i,
            "title": ev["title"],
            "date": ev.get("date"),
            "time": ev.get("time"),
            "location": ev.get("location"),
            "description": (ev.get("description") or "")[:300],  # keep the prompt lean
        })
        id_lookup[i] = ev
    return agent_input, id_lookup


def load_events(path: str = EVENTS_FILE) -> list[dict]:
    with open(path) as f:
        raw_events = json.load(f)
    agent_input, _ = build_agent_input(raw_events)
    return agent_input


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

    array_text = _extract_json_array(raw_text)
    try:
        return json.loads(array_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"agent response looked like a JSON array but failed to parse ({e}) -- "
            f"extracted text: {array_text[:500]!r}"
        ) from e


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
