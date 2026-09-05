"""
One definition of "the same event", shared by scraping and storage.

There used to be three:

  scrape_events.extract_event_id()  numeric id from the URL, else None
                                    (and None meant "never de-duplicate")
  db._event_id()                    numeric id from the URL, else
                                    "title|date"
  build_agent_input()               the event's index in the list

They disagreed, and nothing forced them to agree. The extra event
sources added in September were the first events whose URL is a listing
page rather than a per-event link, so they have no numeric id: scraping
stopped de-duplicating them, and storage then collapsed them onto a
"title|date" primary key and raised UNIQUE constraint failures.

Two rules keep both ends honest:

1. A De Anza numeric event id, when present, is authoritative. The same
   event reached through the category page, the month grid and the
   upcoming list is one event.

2. Otherwise identity is the whole of what a reader would use to tell
   two listings apart -- source, title, date, time and location. Using
   title+date alone merged genuinely different sessions of a recurring
   workshop into one; including time and location keeps the 10am and
   2pm sessions distinct while still collapsing exact repeats.
"""

import re


_EVENT_ID_PATTERN = re.compile(r"id=(\d+)")


def deanza_event_id(url: str | None) -> str | None:
    """Return the numeric De Anza event id embedded in a detail URL."""

    if not url:
        return None

    match = _EVENT_ID_PATTERN.search(url)

    return match.group(1) if match else None


def _normalize(value: str | None) -> str:
    """Collapse whitespace and case so trivial formatting differences
    between two scrapes of the same listing don't create two events."""

    return " ".join((value or "").split()).strip().lower()


def event_identity(event: dict) -> str:
    """
    Return a stable key identifying this event.

    Safe to call on events from any source, at any stage of the
    pipeline, before or after geocoding.
    """

    event_id = deanza_event_id(event.get("url"))

    if event_id:
        return f"deanza:{event_id}"

    parts = [
        _normalize(event.get("source") or "deanza_events"),
        _normalize(event.get("title")),
        _normalize(event.get("date")),
        _normalize(event.get("time")),
        _normalize(event.get("location")),
    ]

    return "listing:" + "|".join(parts)


def deduplicate(events: list[dict]) -> list[dict]:
    """
    Drop repeat listings, keeping the first occurrence of each event.

    Callers control precedence by ordering: scrape_all_events() collects
    category pages first so that the category-labelled copy of an event
    is the one kept.
    """

    seen = set()
    unique = []

    for event in events:
        key = event_identity(event)

        if key in seen:
            continue

        seen.add(key)
        unique.append(event)

    return unique
