import re
from datetime import datetime
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(educational student project; Campus Compass)"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


EXTRA_SOURCES = {
    "student_messages": {
        "url": "https://daweb2.deanza.edu/students/messages/",
        "category": "General",
    },

    "mesa": {
        "url": "https://daweb2.deanza.edu/mesa/",
        "category": "Academic",
    },

    "mstrc": {
        "url": (
            "https://daweb2.deanza.edu/"
            "studentsuccess/mstrc/workshops.html"
        ),
        "category": "Academic",
    },

    "career": {
        "url": (
            "https://daweb2.deanza.edu/"
            "career-center/events/index.html"
        ),
        "category": "Career",
    },

    "academic_skills": {
        "url": (
            "https://daweb2.deanza.edu/"
            "studentsuccess/academicskills/"
        ),
        "category": "Academic",
    },

    "international": {
        "url": (
            "https://www.deanza.edu/"
            "international/workshops.html"
        ),
        "category": "International",
    },
}


def fetch_page(url: str):
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=15,
        )
        response.raise_for_status()
        return response

    except requests.RequestException as exc:
        print(f"[extra source skipped] {url} -- {exc}")
        return None


def scrape_mstrc() -> list[dict]:
    """Scrape MSTRC workshop events."""

    config = EXTRA_SOURCES["mstrc"]
    url = config["url"]

    response = fetch_page(url)

    if response is None:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    events = []

    # --------------------------------------------------
    # Find the year from a heading such as:
    # "Winter 2026 Workshops"
    # --------------------------------------------------

    page_text = soup.get_text(" ", strip=True)

    year_match = re.search(
        r"(?:Winter|Spring|Summer|Fall)\s+(20\d{2})\s+Workshops",
        page_text,
        re.IGNORECASE,
    )

    if year_match:
        workshop_year = int(year_match.group(1))
    else:
        workshop_year = datetime.now().year

    # --------------------------------------------------
    # Read workshop tables
    # --------------------------------------------------

    for row in soup.select("table tr"):

        cells = row.find_all(
            ["td", "th"]
        )

        if len(cells) < 3:
            continue

        values = [
            cell.get_text(
                " ",
                strip=True,
            )
            for cell in cells
        ]

        combined = " ".join(
            values
        ).lower()

        # Skip headers
        if (
            "date" in combined
            and "time" in combined
            and (
                "topic" in combined
                or "workshop" in combined
            )
        ):
            continue

        raw_date = (
            values[0]
            if len(values) > 0
            else ""
        )

        raw_time = (
            values[1]
            if len(values) > 1
            else ""
        )

        title = (
            values[2]
            if len(values) > 2
            else ""
        )

        if not title:
            continue

        # --------------------------------------------------
        # Convert:
        # "Wednesday Jan. 21"
        # →
        # "2026-01-21"
        # --------------------------------------------------

        date_match = re.search(
            r"\b"
            r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\.?\s+"
            r"(\d{1,2})"
            r"\b",
            raw_date,
            re.IGNORECASE,
        )

        if not date_match:
            continue

        month_text = date_match.group(1)
        day_text = date_match.group(2)

        try:
            parsed_date = datetime.strptime(
                f"{month_text} {day_text} {workshop_year}",
                "%b %d %Y",
            )

            date_iso = parsed_date.strftime(
                "%Y-%m-%d"
            )

        except ValueError:
            continue

        # Fix broken spacing such as:
        # "12:0 0 pm" -> "12:00 pm"
        time_text = re.sub(
            r"(?<=\d)\s+(?=\d)",
            "",
            raw_time,
        )

        time_text = re.sub(
            r"\s+",
            " ",
            time_text,
        ).strip()

        events.append(
            {
                "title": title,
                "date": date_iso,
                "time": time_text,
                "location": "MSTRC",
                "category": config["category"],
                "source": "mstrc",
                "description": "MSTRC workshop",
                "url": url,
            }
        )

    print(
        f"MSTRC: found {len(events)} events"
    )

    return events


def scrape_academic_skills() -> list[dict]:
    """Scrape SSC Academic Skills workshops."""

    config = EXTRA_SOURCES["academic_skills"]
    url = config["url"]

    response = fetch_page(url)

    if response is None:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    events = []
    current_date = None

    for row in soup.select("table tr"):

        cells = row.find_all(["td", "th"])

        if not cells:
            continue

        values = [
            re.sub(
                r"\s+",
                " ",
                cell.get_text(" ", strip=True),
            ).strip()
            for cell in cells
        ]

        combined = " ".join(values)

        # ------------------------------------------
        # Skip table headers
        # ------------------------------------------

        combined_lower = combined.lower()

        if (
            "date" in combined_lower
            and "time" in combined_lower
            and "topic" in combined_lower
        ):
            continue

        # ------------------------------------------
        # Find date
        #
        # Example:
        # Wednesday, 01/28/2026
        # ------------------------------------------

        date_found = None

        for value in values:
            match = re.search(
                r"\b"
                r"(\d{1,2})/"
                r"(\d{1,2})/"
                r"(20\d{2})"
                r"\b",
                value,
            )

            if match:
                try:
                    parsed_date = datetime.strptime(
                        match.group(0),
                        "%m/%d/%Y",
                    )

                    date_found = parsed_date.strftime(
                        "%Y-%m-%d"
                    )

                except ValueError:
                    pass

                break

        # Remember the most recent date because
        # later rows may omit the date cell.
        if date_found:
            current_date = date_found

        if not current_date:
            continue

        # ------------------------------------------
        # Ignore non-event rows
        # ------------------------------------------

        if (
            "no workshop" in combined_lower
            or "no workshops" in combined_lower
            or "holiday" in combined_lower
        ):
            continue

        # ------------------------------------------
        # Find time
        #
        # Examples:
        # 12:30 p.m. - 1:20 p.m.
        # 1:30 p.m.-2:20 p.m.
        # ------------------------------------------

        time_index = None
        time_text = None

        for index, value in enumerate(values):

            if re.search(
                r"\b\d{1,2}:\d{2}\s*"
                r"(?:a\.?m\.?|p\.?m\.?)",
                value,
                re.IGNORECASE,
            ):
                time_index = index
                time_text = value
                break

        if time_index is None:
            continue

        # ------------------------------------------
        # The topic normally comes immediately
        # after the time column.
        # ------------------------------------------

        title = ""

        if time_index + 1 < len(values):
            title = values[time_index + 1].strip()

        if not title:
            continue

        # ------------------------------------------
        # Presenter normally follows topic
        # ------------------------------------------

        presenter = ""

        if time_index + 2 < len(values):
            presenter = values[time_index + 2].strip()

        # ------------------------------------------
        # Determine location
        # ------------------------------------------

        location = "Zoom"

        for value in values:
            if value.lower() == "zoom":
                location = "Zoom"
                break

        # ------------------------------------------
        # Clean time formatting
        # ------------------------------------------

        time_text = re.sub(
            r"(?<=\d)\s+(?=\d)",
            "",
            time_text,
        )

        time_text = re.sub(
            r"\s+",
            " ",
            time_text,
        ).strip()

        description = "SSC Academic Skills Workshop"

        if presenter:
            description += f" — Presenter: {presenter}"

        events.append(
            {
                "title": title,
                "date": current_date,
                "time": time_text,
                "location": location,
                "category": config["category"],
                "source": "academic_skills",
                "description": description,
                "url": url,
                "is_virtual": True,
            }
        )

    print(
        f"Academic Skills: found {len(events)} events"
    )

    return events

def scrape_career() -> list[dict]:
    """Scrape Career Center workshops and events."""

    config = EXTRA_SOURCES["career"]
    url = config["url"]

    response = fetch_page(url)

    if response is None:
        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    events = []

    # --------------------------------------------------
    # Find the year from the page.
    # Example:
    # "2026 Spring Career Fair"
    # --------------------------------------------------

    page_text = soup.get_text(" ", strip=True)

    year_match = re.search(
        r"\b(20\d{2})\b",
        page_text,
    )

    if year_match:
        default_year = int(year_match.group(1))
    else:
        default_year = datetime.now().year

    # --------------------------------------------------
    # Career Center stores each event inside an <h4>.
    #
    # Example:
    #
    # SCCOE Hiring Info Session
    # Wednesday, March 11
    # 10 a.m.-12:30p.m.
    # MLC 255
    # --------------------------------------------------

    for heading in soup.find_all("h4"):

        text = re.sub(
            r"\s+",
            " ",
            heading.get_text(
                " ",
                strip=True,
            ),
        ).strip()

        if not text:
            continue

        # --------------------------------------------------
        # Find date
        # --------------------------------------------------

        date_match = re.search(
            r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
            r",?\s+"
            r"(January|February|March|April|May|June|"
            r"July|August|September|October|November|December)"
            r"\s+(\d{1,2})",
            text,
            re.IGNORECASE,
        )

        if not date_match:
            continue

        month_text = date_match.group(1)
        day_text = date_match.group(2)

        # --------------------------------------------------
        # Some events contain their own year.
        # Otherwise use the page year.
        # --------------------------------------------------

        explicit_year = re.search(
            r"\b(20\d{2})\b",
            text[:date_match.start()],
        )

        if explicit_year:
            event_year = int(
                explicit_year.group(1)
            )
        else:
            event_year = default_year

        try:
            parsed_date = datetime.strptime(
                f"{month_text} {day_text} {event_year}",
                "%B %d %Y",
            )

            date_iso = parsed_date.strftime(
                "%Y-%m-%d"
            )

        except ValueError:
            continue

        # --------------------------------------------------
        # Everything before the date = title
        # --------------------------------------------------

        title = text[
            :date_match.start()
        ].strip()

        if not title:
            continue

        # --------------------------------------------------
        # Find time
        #
        # Examples:
        # 10 a.m.-12:30p.m.
        # 11 a.m.-1:00p.m.
        # --------------------------------------------------

        time_match = re.search(
            r"\d{1,2}"
            r"(?::\d{2})?"
            r"\s*"
            r"(?:a\.?m\.?|p\.?m\.?)"
            r"\s*-\s*"
            r"\d{1,2}"
            r"(?::\d{2})?"
            r"\s*"
            r"(?:a\.?m\.?|p\.?m\.?)",
            text,
            re.IGNORECASE,
        )

        if time_match:
            time_text = time_match.group(0)

            time_text = re.sub(
                r"\s+",
                " ",
                time_text,
            ).strip()

        else:
            time_text = ""

        # --------------------------------------------------
        # Everything after the time = location
        # --------------------------------------------------

        location = ""

        if time_match:
            location = text[
                time_match.end():
            ].strip()

        is_virtual = any(
            word in location.lower()
            for word in (
                "zoom",
                "online",
                "virtual",
            )
        )

        events.append(
            {
                "title": title,
                "date": date_iso,
                "time": time_text,
                "location": location,
                "category": config["category"],
                "source": "career",
                "description": "Career Center event",
                "url": url,
                "is_virtual": is_virtual,
            }
        )

    print(
        f"Career Center: found {len(events)} events"
    )

    return events

def scrape_extra_events() -> list[dict]:
    """Scrape all additional De Anza event sources."""

    all_events = []

    scrapers = [
        ("MSTRC", scrape_mstrc),
        ("Academic Skills", scrape_academic_skills),
        ("Career Center", scrape_career),
    ]

    for name, scraper in scrapers:
        try:
            print(f"Fetching extra source: {name}...")

            events = scraper()

            print(
                f"  -> found {len(events)} events"
            )

            all_events.extend(events)

        except Exception as exc:
            print(
                f"  [extra source failed] "
                f"{name} -- {exc}"
            )

    return all_events