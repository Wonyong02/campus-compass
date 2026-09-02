"""
Campus Compass Strands Agent.

This replaces the original calculator / current-time / letter-counter
demo with a tool that works with the real Campus Compass event database
and the existing priority_agent.py personalization logic.

This file is mainly useful for testing the Campus Compass agent directly.
The Flask website continues to use app.py.
"""

import json
from datetime import date

from strands import Agent, tool

import db as eventsdb
from priority_agent import build_agent_input, prioritize_events


@tool
def get_personalized_events(
    year: str,
    major: str,
    interests: list[str] | None = None,
) -> str:
    """
    Get personalized upcoming De Anza College events for a student.

    Args:
        year: Student year, such as freshman or sophomore.
        major: Student major or intended major.
        interests: Student interests, such as transfer, career, or clubs.

    Returns:
        A JSON string containing personalized upcoming events.
    """

    if interests is None:
        interests = []

    events = eventsdb.load_events()

    if not events:
        return json.dumps({
            "error": (
                "No events are currently stored in events.db. "
                "Run the Campus Compass backend and refresh event data first."
            )
        })

    today = date.today().isoformat()

    upcoming_events = [
        event
        for event in events
        if not event.get("date") or event["date"] >= today
    ]

    if not upcoming_events:
        return json.dumps({
            "message": "There are no upcoming events currently stored."
        })

    profile = {
        "year": year,
        "major": major,
        "interests": interests,
    }

    agent_input, id_lookup = build_agent_input(upcoming_events)

    ranked = prioritize_events(
        profile,
        agent_input,
    )

    personalized_events = []
    seen_ids = set()

    if isinstance(ranked, list):
        for item in ranked:
            if not isinstance(item, dict):
                continue

            event_id = item.get("id")

            if event_id not in id_lookup:
                continue

            seen_ids.add(event_id)

            event = dict(id_lookup[event_id])

            event["tier"] = (
                item.get("tier")
                if item.get("tier") in ("high", "medium", "low")
                else "low"
            )

            event["reason"] = (
                item.get("reason")
                or "No reason provided."
            )

            personalized_events.append(event)

    # Keep events even if the ranking agent omitted them.
    for event_id, event_data in id_lookup.items():
        if event_id in seen_ids:
            continue

        event = dict(event_data)
        event["tier"] = "low"
        event["reason"] = (
            "Not ranked by the agent; "
            "shown as low priority by default."
        )

        personalized_events.append(event)

    tier_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }

    personalized_events.sort(
        key=lambda event: (
            tier_order.get(event.get("tier"), 2),
            event.get("date") or "9999-12-31",
        )
    )

    return json.dumps(
        {
            "student_profile": profile,
            "events": personalized_events,
        },
        ensure_ascii=False,
        indent=2,
    )


agent = Agent(
    tools=[
        get_personalized_events,
    ],
)


if __name__ == "__main__":
    message = """
    Find the most important upcoming De Anza College events
    for a sophomore Computer Science student interested in
    transfer opportunities and career development.

    Use the Campus Compass event tool and give me a concise summary
    of the most relevant events.
    """

    agent(message)