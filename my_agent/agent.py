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
from ranking import rank_events


@tool
def get_personalized_events(
    year: str,
    major: str,
    interests: list[str] | None = None,
) -> str:
    """
    Get personalized upcoming De Anza College events for a student.

    Args:
        year: Student stage -- "freshman", "general", or "" for no
            preference. See profile_schema.YEAR_OPTIONS.
        major: Student major or intended major, or "" if undeclared.
        interests: Unused; kept for backwards compatibility.

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

    # Same ranking path the website uses. These two entry points used to
    # carry separate copies of this logic and had drifted apart, so the
    # same event could come back MEDIUM on the map and LOW here.
    personalized_events = rank_events(profile, upcoming_events)

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
    for a first-year Computer Science student.

    Use the Campus Compass event tool and give me a concise summary
    of the most relevant events.
    """

    agent(message)