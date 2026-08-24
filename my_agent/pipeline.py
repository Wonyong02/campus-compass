import json
from datetime import datetime

from scrape_events import scrape_all_events
from geocode_events import geocode_location
from priority_agent import build_agent_input, prioritize_events

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
    agent_input, id_lookup = build_agent_input(raw_events)

    ranked = prioritize_events(STUDENT_PROFILE, agent_input)
    print(f"  -> {len(ranked)} events ranked\n")

    # Same defensive handling as app.py's /api/rerank: don't trust the agent's
    # ids/tiers blindly (a hallucinated id used to crash this whole script
    # with a KeyError), and don't let events the agent skipped just vanish.
    final_events = []
    seen_ids = set()
    for item in ranked if isinstance(ranked, list) else []:
        if not isinstance(item, dict) or item.get("id") not in id_lookup:
            print(f"  [skipped] agent returned an unrecognized id: {item}")
            continue
        seen_ids.add(item["id"])
        ev = id_lookup[item["id"]]
        ev["tier"] = item.get("tier") if item.get("tier") in ("high", "medium", "low") else "low"
        ev["reason"] = item.get("reason") or "No reason given by the agent."
        final_events.append(ev)

    dropped_ids = sorted(set(id_lookup) - seen_ids)
    if dropped_ids:
        print(f"  [note] agent didn't rank {len(dropped_ids)} event(s), added as low priority: {dropped_ids}")
        for i in dropped_ids:
            ev = id_lookup[i]
            ev["tier"] = "low"
            ev["reason"] = "Not ranked by the agent; shown as low priority by default."
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
