import json
from datetime import datetime

from config import PIPELINE_OUTPUT_JSON, SCRAPE_MONTHS_AHEAD
from geocode_events import geocode_location
from ranking import rank_events
from scrape_events import scrape_all_events

# Change this to personalize the pipeline's output for a different
# student. Valid year values come from profile_schema.YEAR_OPTIONS.
STUDENT_PROFILE = {
    "year": "freshman",
    "major": "Computer Science",
    "interests": [],
}

OUTPUT_JSON = PIPELINE_OUTPUT_JSON


def build_pipeline(months_ahead: int = SCRAPE_MONTHS_AHEAD) -> list[dict]:
    print("Step 1/3: Scraping real events from De Anza...")
    raw_events = scrape_all_events(months_ahead=months_ahead)
    print(f"  -> {len(raw_events)} events scraped\n")

    print("Step 2/3: Geocoding locations...")
    for ev in raw_events:
        ev.update(geocode_location(ev.get("location")))
    print("  -> done\n")

    print("Step 3/3: Running Strands Agent to prioritize events...")

    # Shared with app.py and agent.py. The defensive handling that used to
    # be copied here (unrecognized ids, unranked events, tier validation)
    # lives in ranking.py now, and it no longer mutates the caller's dicts.
    final_events = rank_events(STUDENT_PROFILE, raw_events)

    print(f"  -> {len(final_events)} events ranked\n")

    return final_events


if __name__ == "__main__":
    events = build_pipeline()

    with open(OUTPUT_JSON, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "student_profile": STUDENT_PROFILE,
            "events": events,
        }, f, indent=2)

    print(f"Pipeline complete. Saved {len(events)} finalized events to {OUTPUT_JSON}")
