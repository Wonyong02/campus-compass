import json
from datetime import datetime

from scrape_events import scrape_all_events
from geocode_events import geocode_location
from priority_agent import prioritize_events

# Change this to personalize the pipeline's output for a different student
STUDENT_PROFILE = {
    "year": "sophomore",
    "major": "Computer Science",
    "interests": ["career", "academic"],
}

OUTPUT_JSON = "my_agent/campus_events_final.json"


def build_pipeline(months_ahead: int = 3) -> list[dict]:
    print("Step 1/3: Scraping real events from De Anza...")
    raw_events = scrape_all_events(months_ahead=months_ahead)
    print(f"  -> {len(raw_events)} events scraped\n")

    print("Step 2/3: Geocoding locations...")
    for ev in raw_events:
        ev.update(geocode_location(ev.get("location")))
    print("  -> done\n")

    print("Step 3/3: Running Strands Agent to prioritize events...")
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
            "description": (ev.get("description") or "")[:300],
        })
        id_lookup[i] = ev

    ranked = prioritize_events(STUDENT_PROFILE, agent_input)
    print(f"  -> {len(ranked)} events ranked\n")

    final_events = []
    for item in ranked:
        ev = id_lookup[item["id"]]
        ev["tier"] = item["tier"]
        ev["reason"] = item["reason"]
        final_events.append(ev)

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
