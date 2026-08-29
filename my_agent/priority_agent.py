import json
from datetime import datetime

from strands import Agent

from event_category_map import (
    MAJOR_EVENT_CATEGORIES,
    GENERAL_EVENT_CATEGORIES,
)


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
    """
    Return the broader major family for a student's selected major.
    """

    if not major:
        return "Undeclared / General"

    if major == "Undeclared / Undecided":
        return "Undeclared / General"

    for family, majors in MAJOR_FAMILIES.items():
        if major in majors:
            return family

    return "Other / General"


def get_relevant_event_categories(major: str) -> list[str]:
    """
    Return De Anza event categories that are especially relevant
    to the student's selected major.
    """

    if not major:
        return []

    return MAJOR_EVENT_CATEGORIES.get(
        major,
        [],
    )


PRIORITY_SYSTEM_PROMPT = """
You are a campus event prioritization assistant.

You will be given:
- today's date
- a student profile containing:
  - year
  - major
  - major_family
  - interests
  - relevant_event_categories
  - general_event_categories
- a list of real campus events
- each event may contain a De Anza event category

Rank EVERY event for the student.

IMPORTANT RULES:

1. The exact major is a strong personalization signal, but it is NOT a filter.

2. Use major_family to understand related fields.

Events related to the student's broader major family should still be
considered relevant even when they do not exactly match the major name.

For example, an Art student may still benefit from design, photography,
film, or other Art / Design / Media events.

3. Use De Anza's real event categories as grounding data.

If an event's category appears in the student's
relevant_event_categories, treat that as a strong relevance signal.

However, category matching is NOT an automatic HIGH priority.
Also consider the event title, description, urgency, year, and interests.

4. Some event categories are broadly useful regardless of major.

If an event's category appears in general_event_categories,
do not lower its priority simply because it is unrelated to
the student's major.

5. Transfer, UC/CSU applications, TAG, registration, enrollment,
financial aid, scholarships, graduation, academic deadlines,
and major campus-wide announcements should not become LOW merely
because they are unrelated to the student's major.

6. Transfer information should be considered useful across majors.

Use the student's year and the timing of the event to decide
how urgent it is.

7. Interests are preference signals, not filters.

8. Consider urgency as well as relevance.

An event happening soon may deserve higher priority than a similar
event happening much later.

9. Personalization should BOOST relevant opportunities,
not hide generally important student information.

10. An event may have no category.

If category is null or missing, judge the event using its title,
description, date, location, student major, major_family,
interests, and general importance.

Priority guidance:

HIGH:
- urgent and broadly important
- OR especially relevant to the student's exact major
- OR strongly relevant through a matching De Anza event category
- OR highly valuable for the student's major family and interests

MEDIUM:
- useful to most students
- OR relevant to the student's broader major family
- OR generally important but not urgent
- OR somewhat related to the student's relevant event categories

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
    return Agent(
        system_prompt=PRIORITY_SYSTEM_PROMPT
    )


def _extract_json_array(text: str) -> str:
    """
    Pulls the first balanced top-level [...] block out of the agent's
    raw response, ignoring brackets inside quoted strings.

    Raises ValueError with part of the raw response if parsing fails.
    """

    start = text.find("[")

    if start == -1:
        raise ValueError(
            "agent response contained no JSON array at all -- "
            f"raw response: {text[:500]!r}"
        )

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

    raise ValueError(
        "agent response had an unclosed JSON array "
        "(unbalanced brackets) -- "
        f"raw response: {text[:500]!r}"
    )


def build_agent_input(
    raw_events: list[dict],
) -> tuple[list[dict], dict[int, dict]]:
    """
    Turns raw scraped events into the trimmed format sent to the AI.

    Includes the official De Anza event category so the agent can use
    category-to-major relationships as grounding information.

    Returns:
        agent_input:
            trimmed event data sent to the model

        id_lookup:
            maps generated IDs back to the original event dictionaries
    """

    agent_input = []
    id_lookup = {}

    for i, ev in enumerate(raw_events):

        if not ev.get("title"):
            continue

        agent_input.append({
            "id": i,
            "title": ev["title"],
            "date": ev.get("date"),
            "time": ev.get("time"),
            "location": ev.get("location"),

            # Official De Anza event category
            "category": ev.get("category"),

            "description": (
                ev.get("description") or ""
            )[:300],
        })

        id_lookup[i] = ev

    return agent_input, id_lookup


def load_events(
    path: str = EVENTS_FILE,
) -> list[dict]:
    """
    Load scraped De Anza events and convert them into the
    trimmed agent-input format.
    """

    with open(
        path,
        encoding="utf-8",
    ) as f:
        raw_events = json.load(f)

    agent_input, _ = build_agent_input(
        raw_events
    )

    return agent_input


def prioritize_events(
    student_profile: dict,
    events: list[dict],
) -> list[dict]:
    """
    Ask the Strands agent to rank all events for one student profile.
    """

    agent = build_agent()

    profile_for_agent = dict(
        student_profile
    )

    major = student_profile.get(
        "major",
        "",
    )

    # Existing broader major grouping
    profile_for_agent["major_family"] = (
        get_major_family(major)
    )

    # NEW:
    # Official De Anza event categories related to this major
    profile_for_agent[
        "relevant_event_categories"
    ] = get_relevant_event_categories(
        major
    )

    # NEW:
    # Categories that are useful regardless of major
    profile_for_agent[
        "general_event_categories"
    ] = GENERAL_EVENT_CATEGORIES

    payload = {
        "today": datetime.now().strftime(
            "%Y-%m-%d"
        ),
        "student_profile": profile_for_agent,
        "events": events,
    }

    prompt = (
        "Here is the data:\n"
        + json.dumps(
            payload,
            indent=2,
        )
    )

    response = agent(prompt)

    raw_text = str(response)

    array_text = _extract_json_array(
        raw_text
    )

    try:
        return json.loads(
            array_text
        )

    except json.JSONDecodeError as e:
        raise ValueError(
            "agent response looked like a JSON array "
            f"but failed to parse ({e}) -- "
            f"extracted text: {array_text[:500]!r}"
        ) from e


if __name__ == "__main__":

    # Test profile
    student_profile = {
        "year": "sophomore",
        "major": "Computer Science",
        "interests": [
            "career",
            "academic",
        ],
    }

    events = load_events()

    print(
        f"Loaded {len(events)} real events "
        f"from {EVENTS_FILE}\n"
    )

    # Useful debugging information
    print(
        "Major family:",
        get_major_family(
            student_profile["major"]
        ),
    )

    print(
        "Relevant De Anza categories:",
        get_relevant_event_categories(
            student_profile["major"]
        ),
    )

    print(
        "General categories:",
        GENERAL_EVENT_CATEGORIES,
    )

    print()

    ranked = prioritize_events(
        student_profile,
        events,
    )

    print(
        "=== Prioritized Real Events ==="
    )

    for item in ranked:

        event = next(
            e
            for e in events
            if e["id"] == item["id"]
        )

        print(
            f"[{item['tier'].upper():6}] "
            f"{event['title']} "
            f"({event['date']})  —  "
            f"{item['reason']}"
        )