import json
from datetime import datetime

from strands import Agent

EVENTS_FILE = "my_agent/deanza_events.json"
MAJOR_FAMILIES = {
    "Technology / Engineering / STEM": [
        "Computer Science",
        "Data Science",
        "Cybersecurity",
        "Engineering",
        "Mathematics",
        "Physics",
    ],

    "Art / Design / Media": [
        "Art",
        "Art History",
        "Studio Art",
        "Graphic Design",
        "Photography",
        "Film / Television",
        "Music",
    ],

    "Life Science / Health": [
        "Biology",
        "Chemistry",
        "Health Sciences",
        "Nursing",
        "Public Health",
        "Kinesiology",
    ],

    "Business / Economics": [
        "Accounting",
        "Business Administration",
        "Economics",
    ],

    "Social / Behavioral Sciences": [
        "Anthropology",
        "Communication Studies",
        "Political Science",
        "Psychology",
        "Sociology",
        "Administration of Justice",
    ],

    "Humanities / Language": [
        "English",
        "History",
        "Humanities",
        "Linguistics",
        "Philosophy",
        "Journalism",
    ],

    "Environment / Earth Science": [
        "Environmental Science",
        "Geography",
        "Geology",
    ],

    "Education / Human Services": [
        "Child Development",
    ],

    "Law / Legal Studies": [
        "Paralegal Studies",
    ],
}


def get_major_family(major: str) -> str:
    if not major:
        return "Undeclared / General"

    if major == "Undeclared / Undecided":
        return "Undeclared / General"

    for family, majors in MAJOR_FAMILIES.items():
        if major in majors:
            return family

    return "Other / General"

PRIORITY_SYSTEM_PROMPT = """
You are a campus event prioritization assistant.

You will be given:
- today's date
- a student profile containing year, major, major_family, and interests
- a list of real campus events

Rank EVERY event for the student.

IMPORTANT RULES:

1. The exact major is a strong personalization signal, but it is NOT a filter.

2. Use major_family to understand related fields.
Events related to the student's broader major family should still be
considered relevant even when they do not exactly match the major name.

For example, an Art student may still benefit from design, photography,
film, or other Art / Design / Media events.

3. Some information is broadly important regardless of major.
Transfer, UC/CSU applications, TAG, registration, enrollment,
financial aid, scholarships, graduation, academic deadlines,
and major campus-wide announcements should not become LOW merely
because they are unrelated to the student's major.

4. Transfer information should be considered useful across majors.
Use the student's year to decide how urgent it is.

5. Interests are preference signals, not filters.

6. Consider urgency as well as relevance.

7. Personalization should BOOST relevant opportunities,
not hide generally important student information.

Priority guidance:

HIGH:
- urgent and broadly important
- OR especially relevant to the student's exact major
- OR highly valuable for the student's major family and interests

MEDIUM:
- useful to most students
- OR relevant to the student's broader major family
- OR generally important but not urgent

LOW:
- genuinely unlikely to be useful to this student

Do NOT assign LOW only because an event does not exactly match
the student's major.

Respond ONLY with a JSON array.

Each item must look exactly like:
{
  "id": <event id, integer>,
  "tier": "high" | "medium" | "low",
  "reason": "<one short sentence, under 15 words>"
}

Rank ALL events from most to least important.
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
    profile_for_agent = dict(student_profile)
    profile_for_agent["major_family"] = get_major_family(
        student_profile.get("major", "")
    )

    payload = {
        "today": datetime.now().strftime("%Y-%m-%d"),
        "student_profile": profile_for_agent,
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
