import json
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from event_category_map import CATEGORY_SOURCES


HEADERS = {
    "User-Agent": "Mozilla/5.0 (educational hackathon project; contact: you@example.com)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

CURRENT_YEAR = datetime.now().year
REQUEST_DELAY_SECONDS = 2  # be polite -- don't hammer the school's server


def parse_date_heading(text: str) -> str | None:
    """Turns 'Aug 25 - Tuesday' into '2026-08-25'."""
    match = re.match(r"([A-Za-z]{3})\s+(\d{1,2})", text)

    if not match:
        return None

    month_str, day_str = match.groups()

    try:
        parsed = datetime.strptime(
            f"{month_str} {day_str} {CURRENT_YEAR}",
            "%b %d %Y",
        )
        return parsed.strftime("%Y-%m-%d")

    except ValueError:
        return None


def is_past_event(event: dict, today_iso: str) -> bool:
    """
    True only when the event has a parsed date AND it's before today.

    Events with no date at all (e.g. some deadline-style entries) are
    NOT treated as past -- we simply don't know, and hiding them would
    be a false negative, not an honest "this already happened."
    """
    date = event.get("date")
    return bool(date) and date < today_iso


def fetch(url: str) -> requests.Response | None:
    """Fetches a URL, returning None instead of crashing on failure."""
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=10,
        )

        response.raise_for_status()
        return response

    except requests.exceptions.HTTPError as e:
        print(f"  [skipped] {url} -- {e}")
        return None

    except requests.exceptions.RequestException as e:
        print(f"  [skipped] {url} -- connection error: {e}")
        return None

def scrape_upcoming_list(
    url: str = "https://deanza.edu/events/",
) -> list[dict]:
    """
    Scrapes an Upcoming Events-style page.

    Works with both:
    - the general De Anza events page
    - category-specific event pages

    Some De Anza category pages use slightly different CSS classes,
    so this scraper falls back to plain h4/h3 tags when needed.
    """

    response = fetch(url)

    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    detail_links = soup.find_all(
        "a",
        href=lambda h: h and "event.html?id=" in h,
    )

    events = []

    for link in detail_links:

        # Try the original specific selectors first.
        title_tag = link.find_previous(
            "h4",
            class_="event-title",
        )

        date_tag = link.find_previous(
            "h3",
            class_="mb-0",
        )

        # Some category pages don't use those CSS classes.
        if not title_tag:
            title_tag = link.find_previous("h4")

        if not date_tag:
            date_tag = link.find_previous("h3")

        if not title_tag or not date_tag:
            continue

        title = title_tag.get_text(strip=True)

        date_iso = parse_date_heading(
            date_tag.get_text(strip=True)
        )

        # Try to find the full event container.
        block = link.find_parent(
            "div",
            class_="col-md-12",
        )

        # Do not throw away the entire event just because
        # the page uses a different container structure.
        if block:

            time_tag = block.find(
                "span",
                class_="fa-clock",
            )

            time_text = (
                time_tag.find_parent("p").get_text(strip=True)
                if time_tag
                else None
            )

            location_tag = block.find(
                "span",
                class_="fa-map-marker-alt",
            )

            location_text = (
                location_tag.find_parent("p").get_text(strip=True)
                if location_tag
                else None
            )

            category_tag = block.find(
                "span",
                class_="label-primary",
            )

            category = (
                category_tag.get_text(strip=True)
                if category_tag
                else None
            )

            hr_tag = block.find(
                "hr",
                class_="hr-grey",
            )

            description = (
                hr_tag.find_next("p").get_text(strip=True)
                if hr_tag
                else None
            )

        else:
            time_text = None
            location_text = None
            category = None
            description = None

        relative_url = link.get("href")

        if relative_url and relative_url.startswith("http"):
            full_url = relative_url

        elif relative_url:
            if not relative_url.startswith("/"):
                relative_url = "/" + relative_url

            full_url = (
                "https://deanza.edu"
                + relative_url
            )

        else:
            full_url = None

        events.append(
            {
                "title": title,
                "date": date_iso,
                "time": time_text,
                "location": location_text,
                "category": category,
                "description": description,
                "url": full_url,
            }
        )

    return events


def scrape_category_page(
    category_name: str,
    url: str,
) -> list[dict]:
    """
    Scrape one De Anza event category page.

    Because we already know which category URL we are visiting,
    every event found on this page gets that category name.
    """

    events = scrape_upcoming_list(url)

    for event in events:
        event["category"] = category_name

    return events


def scrape_month_view(
    month: int,
    year: int,
) -> list[dict]:
    """
    Scrapes the Events By Month calendar page.

    Month-view events may not contain reliable category information,
    so category remains None here.
    """

    url = (
        "https://deanza.edu/events/month.html"
        f"?m={month:02d}&y={year}"
    )

    response = fetch(url)

    if response is None:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    events = []

    for day_cell in soup.find_all(
        "td",
        class_="day",
    ):
        time_tag = day_cell.find("time")

        date_iso = (
            time_tag["datetime"]
            if time_tag
            and time_tag.has_attr("datetime")
            else None
        )

        for event_div in day_cell.find_all(
            "div",
            class_="event",
        ):
            title_tag = event_div.find("h3")
            desc_tag = event_div.find(
                "div",
                class_="desc",
            )

            location_tag = event_div.find(
                "div",
                class_="location",
            )

            datetime_tag = event_div.find(
                "div",
                class_="datetime",
            )

            link_tag = event_div.find(
                "div",
                class_="link",
            )

            relative_url = (
                link_tag.get_text(strip=True)
                if link_tag
                else None
            )

            if relative_url and relative_url.startswith("http"):
                full_url = relative_url

            elif relative_url:
                if not relative_url.startswith("/"):
                    relative_url = "/" + relative_url

                full_url = (
                    "https://deanza.edu"
                    + relative_url
                )

            else:
                full_url = None

            events.append(
                {
                    "title": (
                        title_tag.get_text(strip=True)
                        if title_tag
                        else None
                    ),
                    "date": date_iso,
                    "time": (
                        datetime_tag.get_text(strip=True)
                        if datetime_tag
                        else None
                    ),
                    "location": (
                        location_tag.get_text(strip=True)
                        if location_tag
                        else None
                    ),
                    "category": None,
                    "description": (
                        desc_tag.get_text(strip=True)
                        if desc_tag
                        else None
                    ),
                    "url": full_url,
                }
            )

    return events


def extract_event_id(
    url: str | None,
) -> str | None:
    """Extracts the numeric event ID from an event URL."""

    if not url:
        return None

    match = re.search(
        r"id=(\d+)",
        url,
    )

    return match.group(1) if match else None


def scrape_all_events(
    months_ahead: int = 3,
) -> list[dict]:
    """
    Combines:
    1. Category-specific event pages
    2. General Upcoming Events page
    3. Several months of the calendar

    Category pages are scraped FIRST so that category-labeled versions
    of events are kept during de-duplication.
    """

    all_events = []

    # --------------------------------------------------
    # 1. CATEGORY-SPECIFIC EVENTS
    # --------------------------------------------------

    for category_name, url in CATEGORY_SOURCES.items():
        print(
            f"Fetching category: {category_name}..."
        )

        category_events = scrape_category_page(
            category_name,
            url,
        )

        print(f"  -> found {len(category_events)} events")

        all_events.extend(
            category_events
        )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    # --------------------------------------------------
    # 2. GENERAL UPCOMING EVENTS
    # --------------------------------------------------

    print(
        "Fetching upcoming events list..."
    )

    upcoming_events = scrape_upcoming_list()

    all_events.extend(
        upcoming_events
    )

    time.sleep(
        REQUEST_DELAY_SECONDS
    )

    # --------------------------------------------------
    # 3. MONTH VIEW
    # --------------------------------------------------

    today = datetime.now()

    for i in range(months_ahead):
        month = (
            (today.month - 1 + i) % 12
        ) + 1

        year = today.year + (
            (today.month - 1 + i) // 12
        )

        print(
            f"Fetching month view for "
            f"{month:02d}/{year}..."
        )

        month_events = scrape_month_view(
            month,
            year,
        )

        all_events.extend(
            month_events
        )

        time.sleep(
            REQUEST_DELAY_SECONDS
        )

    # --------------------------------------------------
    # 4. REMOVE DUPLICATES
    # --------------------------------------------------

    seen_ids = set()
    deduped = []

    for ev in all_events:
        event_id = extract_event_id(
            ev.get("url")
        )

        if event_id and event_id in seen_ids:
            continue

        if event_id:
            seen_ids.add(event_id)

        deduped.append(ev)

    # --------------------------------------------------
    # 5. DROP EVENTS THAT HAVE ALREADY HAPPENED
    # --------------------------------------------------
    # Root-level filter: scrape_month_view() above always scrapes the
    # WHOLE current month (including days before today), and De Anza's
    # own pages don't filter this out either. Nothing downstream
    # (db.py, app.py) re-checks dates, so this is the one place that
    # actually needs to do it -- everything after this point should be
    # able to assume "every event here is today or later."
    today_iso = datetime.now().strftime("%Y-%m-%d")

    deduped = [
        ev for ev in deduped
        if not is_past_event(ev, today_iso)
    ]

    return deduped


if __name__ == "__main__":
    events = scrape_all_events(
        months_ahead=3
    )

    print(
        f"\nScraped {len(events)} "
        f"unique events total.\n"
    )

    print(
        json.dumps(
            events[:5],
            indent=2,
        )
    )

    with open(
        "my_agent/deanza_events.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            events,
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"\nSaved all {len(events)} events "
        f"to my_agent/deanza_events.json"
    )