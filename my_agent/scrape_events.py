import json
import re
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

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
        parsed = datetime.strptime(f"{month_str} {day_str} {CURRENT_YEAR}", "%b %d %Y")
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return None


def fetch(url: str) -> requests.Response | None:
    """Fetches a URL, returning None (instead of crashing) on failure."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        return response
    except requests.exceptions.HTTPError as e:
        print(f"  [skipped] {url} -- {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  [skipped] {url} -- connection error: {e}")
        return None


def scrape_upcoming_list(url: str = "https://www.deanza.edu/events/") -> list[dict]:
    """Scrapes the 'Upcoming Events' list page (near-term, most detailed)."""
    response = fetch(url)
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    detail_links = soup.find_all("a", href=lambda h: h and "event.html?id=" in h)

    events = []
    for link in detail_links:
        title_tag = link.find_previous("h4", class_="event-title")
        date_tag = link.find_previous("h3", class_="mb-0")
        if not title_tag or not date_tag:
            continue

        title = title_tag.get_text(strip=True)
        date_iso = parse_date_heading(date_tag.get_text(strip=True))

        block = link.find_parent("div", class_="col-md-12")
        time_tag = block.find("span", class_="fa-clock")
        time_text = time_tag.find_parent("p").get_text(strip=True) if time_tag else None

        location_tag = block.find("span", class_="fa-map-marker-alt")
        location_text = location_tag.find_parent("p").get_text(strip=True) if location_tag else None

        category_tag = block.find("span", class_="label-primary")
        category = category_tag.get_text(strip=True) if category_tag else None

        hr_tag = block.find("hr", class_="hr-grey")
        description = hr_tag.find_next("p").get_text(strip=True) if hr_tag else None

        events.append({
            "title": title,
            "date": date_iso,
            "time": time_text,
            "location": location_text,
            "category": category,
            "description": description,
            "url": "https://www.deanza.edu" + link["href"],
        })
    return events


def scrape_month_view(month: int, year: int) -> list[dict]:
    """Scrapes the 'Events By Month' calendar-grid page (reaches further out)."""
    url = f"https://www.deanza.edu/events/month.html?m={month:02d}&y={year}"
    response = fetch(url)
    if response is None:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    events = []
    for day_cell in soup.find_all("td", class_="day"):
        time_tag = day_cell.find("time")
        date_iso = time_tag["datetime"] if time_tag and time_tag.has_attr("datetime") else None

        for event_div in day_cell.find_all("div", class_="event"):
            title_tag = event_div.find("h3")
            desc_tag = event_div.find("div", class_="desc")
            location_tag = event_div.find("div", class_="location")
            datetime_tag = event_div.find("div", class_="datetime")
            link_tag = event_div.find("div", class_="link")

            relative_url = link_tag.get_text(strip=True) if link_tag else None
            full_url = "https://www.deanza.edu" + relative_url if relative_url else None

            events.append({
                "title": title_tag.get_text(strip=True) if title_tag else None,
                "date": date_iso,
                "time": datetime_tag.get_text(strip=True) if datetime_tag else None,
                "location": location_tag.get_text(strip=True) if location_tag else None,
                "category": None,
                "description": desc_tag.get_text(strip=True) if desc_tag else None,
                "url": full_url,
            })
    return events


def extract_event_id(url: str | None) -> str | None:
    if not url:
        return None
    match = re.search(r"id=(\d+)", url)
    return match.group(1) if match else None


def scrape_all_events(months_ahead: int = 3) -> list[dict]:
    """
    Combines the near-term list page with several months of the calendar
    grid, de-duplicating by event ID. Requests are spaced out and failures
    on individual months are skipped rather than crashing the whole run.
    """
    print("Fetching upcoming events list...")
    all_events = scrape_upcoming_list()
    time.sleep(REQUEST_DELAY_SECONDS)

    today = datetime.now()
    for i in range(months_ahead):
        month = ((today.month - 1 + i) % 12) + 1
        year = today.year + ((today.month - 1 + i) // 12)
        print(f"Fetching month view for {month:02d}/{year}...")
        all_events.extend(scrape_month_view(month, year))
        time.sleep(REQUEST_DELAY_SECONDS)

    seen_ids = set()
    deduped = []
    for ev in all_events:
        event_id = extract_event_id(ev["url"])
        if event_id and event_id in seen_ids:
            continue
        if event_id:
            seen_ids.add(event_id)
        deduped.append(ev)

    return deduped


if __name__ == "__main__":
    events = scrape_all_events(months_ahead=3)
    print(f"\nScraped {len(events)} unique events total.\n")
    print(json.dumps(events[:5], indent=2))

    with open("my_agent/deanza_events.json", "w") as f:
        json.dump(events, f, indent=2)
    print(f"\nSaved all {len(events)} events to my_agent/deanza_events.json")
