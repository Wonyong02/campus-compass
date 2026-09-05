import json

from config import EVENTS_GEOCODED_JSON, EVENTS_JSON

EVENTS_FILE = EVENTS_JSON
OUTPUT_FILE = EVENTS_GEOCODED_JSON

# Coordinates confirmed via Google Places (real, verified locations)
CAMPUS_CENTER = (37.3192806, -122.0447919)

# Campus-wide names, not buildings. Checked only after every specific
# building key has failed: "de anza college" is a substring of most
# on-campus location strings, so matching it first resolved
# "De Anza College Planetarium" to the campus centre and labelled the
# result "confirmed" -- a wrong coordinate presented as an exact one.
CAMPUS_WIDE = [
    "de anza college",
    "de anza campus",
]

CONFIRMED = {
    "registration": (37.321623, -122.0447979),
    "student services": (37.321623, -122.0447979),
    "transfer center": (37.321623, -122.0447979),  # located inside the RSS building
    "hinson campus center": (37.320816, -122.0455674),
    "campus center": (37.320816, -122.0455674),
}

# Not independently listed on Google Places (these are informal internal
# nicknames for buildings, not separately indexed businesses). Positions
# below are hand-estimated relative to the confirmed campus center and
# marked "approximate" -- a production version should pull exact
# coordinates from the school's own campus map/GIS data instead.
APPROXIMATE = {
    "social sciences and humanities": (37.3184, -122.0453),
    "l-73": (37.3184, -122.0453),
    "l 73": (37.3184, -122.0453),
    "physical sciences": (37.3199, -122.0438),
    "s55": (37.3199, -122.0438),
    "health & life sciences": (37.3187, -122.0463),
    "health and life sciences": (37.3187, -122.0463),
    "sem 2": (37.3187, -122.0463),
    "business & finance": (37.3178, -122.0441),
    "business and finance": (37.3178, -122.0441),
    "advanced technology center": (37.3178, -122.0441),
    "at 202": (37.3178, -122.0441),
    "at202": (37.3178, -122.0441),
    "language and communications": (37.3182, -122.0450),
    "l 43": (37.3182, -122.0450),
    "artistic expression": (37.3190, -122.0470),
    "l21": (37.3190, -122.0470),
    "planetarium": (37.3195, -122.0455),
    "parking lot": (37.3205, -122.0430),
    "main quad": (37.3192, -122.0448),
}

VIRTUAL_KEYWORDS = ["online", "zoom", "virtual", "webinar"]


def geocode_location(location_text: str | None) -> dict:
    if not location_text:
        return {"latitude": None, "longitude": None, "is_virtual": False, "match_type": "none"}

    text_lower = location_text.lower()

    if any(keyword in text_lower for keyword in VIRTUAL_KEYWORDS):
        return {"latitude": None, "longitude": None, "is_virtual": True, "match_type": "virtual"}

    # Longest key first, across both tables. "de anza college" is a
    # substring of most on-campus location strings, so checking all of
    # CONFIRMED before APPROXIMATE resolved "De Anza College Planetarium"
    # to the campus centre -- and labelled it "confirmed", so the UI
    # showed a wrong coordinate without the "~" it uses for imprecise ones.
    candidates = [
        (keyword, coords, "confirmed")
        for keyword, coords in CONFIRMED.items()
    ] + [
        (keyword, coords, "approximate")
        for keyword, coords in APPROXIMATE.items()
    ]

    for keyword, (lat, lng), match_type in sorted(
        candidates,
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        if keyword in text_lower:
            return {
                "latitude": lat,
                "longitude": lng,
                "is_virtual": False,
                "match_type": match_type,
            }

    lat, lng = CAMPUS_CENTER

    # An explicit campus-wide name: the campus centre really is the right
    # coordinate, so this one is "confirmed".
    if any(keyword in text_lower for keyword in CAMPUS_WIDE):
        return {"latitude": lat, "longitude": lng, "is_virtual": False, "match_type": "confirmed"}

    # Anything unrecognised still gets a pin rather than being dropped,
    # but is flagged so the UI can mark it imprecise.
    return {"latitude": lat, "longitude": lng, "is_virtual": False, "match_type": "fallback_campus_center"}


def geocode_all_events(path: str = EVENTS_FILE) -> list[dict]:
    with open(path) as f:
        events = json.load(f)

    for event in events:
        geo = geocode_location(event.get("location"))
        event.update(geo)

    return events


if __name__ == "__main__":
    events = geocode_all_events()

    counts = {"confirmed": 0, "approximate": 0, "fallback_campus_center": 0, "virtual": 0, "none": 0}
    for e in events:
        counts[e["match_type"]] += 1

    print("Geocoding summary:")
    for match_type, count in counts.items():
        print(f"  {match_type}: {count}")

    print()
    for e in events:
        loc_display = "virtual (no pin)" if e["is_virtual"] else f"({e['latitude']}, {e['longitude']})"
        print(f"[{e['match_type']:20}] {e['title']}  ->  {loc_display}")

    with open(OUTPUT_FILE, "w") as f:
        json.dump(events, f, indent=2)
    print(f"\nSaved geocoded events to {OUTPUT_FILE}")
