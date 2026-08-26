"""
Flask backend for Campus Compass.

Two things live here:

1. Live profile re-ranking (POST /api/rerank) -- see PROJECT_LOG.md
   section 11. Changing the student's profile used to mean editing
   pipeline.py's hardcoded STUDENT_PROFILE and re-running it by hand.
   This exposes the same re-ranking step (priority_agent) as an HTTP
   endpoint so campus_map_prototype.html's profile panel can call it
   live instead.

2. A real events database (my_agent/db.py, SQLite) instead of a plain
   JSON cache file -- "최소 Database 도입", priority #2 on the
   post-hackathon-review punch list. Scraping is still kept OUT of the
   per-request path on purpose: De Anza's server gets rate-limited fast
   (see PROJECT_LOG.md section 7), and the scrape doesn't change when a
   student's profile changes. So events are scraped + geocoded once and
   persisted to events.db; every /api/rerank call only re-runs the
   Strands Agent's judgment against that stored event list.

There is deliberately no login here. The product direction is: a
student sets their year/major/interests once, the AI re-ranks against
real events, and the browser remembers that profile itself (see
localStorage usage in campus_map_prototype.html) -- no account needed
just to get a personalized map. See db.py's module docstring for where
Users/Preferences tables would go if/when that changes.

Run:
    pip install -r requirements.txt
    python my_agent/app.py
Serves on http://localhost:5001
"""
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

import db as eventsdb
from scrape_events import scrape_all_events
from geocode_events import geocode_location
from priority_agent import build_agent_input, prioritize_events

app = Flask(__name__)
CORS(app)  # the map page is opened as a local file / localhost, so allow any origin

_events_cache = None

GENERAL_IMPORTANT_KEYWORDS = [
    "transfer",
    "tag",
    "uc application",
    "csu application",
    "registration",
    "enrollment",
    "financial aid",
    "scholarship",
    "graduation",
    "academic deadline",
]


def is_generally_important_event(event: dict) -> bool:
    text = " ".join([
        event.get("title") or "",
        event.get("description") or "",
    ]).lower()

    return any(keyword in text for keyword in GENERAL_IMPORTANT_KEYWORDS)


def load_or_scrape_events(force_refresh: bool = False) -> list[dict]:
    """Returns the scraped+geocoded event list, backed by events.db so we
    don't hit De Anza's server on every profile change or app restart."""
    global _events_cache

    if _events_cache is not None and not force_refresh:
        return _events_cache

    if not force_refresh:
        cached = eventsdb.load_events()
        if cached is not None:
            _events_cache = cached
            return _events_cache

    print("Scraping + geocoding fresh De Anza events (hits the live site, please be patient)...")
    raw_events = scrape_all_events(months_ahead=3)
    for ev in raw_events:
        ev.update(geocode_location(ev.get("location")))

    eventsdb.save_events(raw_events, scraped_at=datetime.now().isoformat())

    _events_cache = raw_events
    return _events_cache


@app.route("/api/rerank", methods=["POST"])
def rerank():
    """
    Body: { "year": "...", "major": "...", "interests": ["...", "..."] }

    Returns the same shape pipeline.py writes to campus_events_final.json
    (generated_at / student_profile / events), computed live for whatever
    profile was just posted.
    """
    profile = request.get_json(force=True) or {}
    if not profile.get("year") or not profile.get("major"):
        return jsonify({"error": "year and major are required"}), 400
    profile.setdefault("interests", [])

    raw_events = load_or_scrape_events()
    agent_input, id_lookup = build_agent_input(raw_events)

    try:
        ranked = prioritize_events(profile, agent_input)
    except Exception as e:  # Bedrock call failed / bad JSON back from the agent, etc.
        return jsonify({"error": f"Agent re-ranking failed: {e}"}), 502

    # The agent's output is untrusted: it can hallucinate an id that was never
    # in agent_input, return a tier that isn't high/medium/low, or simply omit
    # some events from the ranking instead of scoring them. None of that
    # should crash the request (a raw KeyError used to bubble up here as an
    # unhandled 500) or silently vanish events from the map -- so validate as
    # we go and fall back to a safe default per event instead.
    final_events = []
    seen_ids = set()
    skipped_ids = []
    for item in ranked if isinstance(ranked, list) else []:
        if not isinstance(item, dict) or item.get("id") not in id_lookup:
            skipped_ids.append(item.get("id") if isinstance(item, dict) else item)
            continue
        seen_ids.add(item["id"])
        ev = dict(id_lookup[item["id"]])
        ev["tier"] = item.get("tier") if item.get("tier") in ("high", "medium", "low") else "low"
        ev["reason"] = item.get("reason") or "No reason given by the agent."

        # Broadly important student information should never be hidden as LOW
        # just because it does not match the student's major.
        if ev["tier"] == "low" and is_generally_important_event(ev):
            ev["tier"] = "medium"
            ev["reason"] = "Broadly useful student information regardless of major."

        final_events.append(ev)

    if skipped_ids:
        print(f"[rerank] agent returned {len(skipped_ids)} unrecognized id(s), skipped: {skipped_ids}")

    # Events the agent dropped from its ranking entirely still get shown --
    # as low priority with a generic reason -- rather than disappearing from
    # the map without explanation.
    dropped_ids = sorted(set(id_lookup) - seen_ids)
    if dropped_ids:
        print(f"[rerank] agent didn't rank {len(dropped_ids)} event(s), added as low priority: {dropped_ids}")
        for i in dropped_ids:
            ev = dict(id_lookup[i])

            if is_generally_important_event(ev):
                ev["tier"] = "medium"
                ev["reason"] = "Broadly useful student information regardless of major."
            else:
                ev["tier"] = "low"
                ev["reason"] = "Not ranked by the agent; shown as low priority by default."

            final_events.append(ev)

    tier_order = {
    "high": 0,
    "medium": 1,
    "low": 2,
    }

    final_events.sort(key=lambda ev: tier_order.get(ev.get("tier"), 2))

    return jsonify({
        "generated_at": datetime.now().isoformat(),
        "student_profile": profile,
        "events": final_events,
    })


@app.route("/api/categories", methods=["GET"])
def categories():
    """Real category labels seen in the scraped events (e.g. from the
    De Anza list page's badges), so the profile panel can offer actual
    categories instead of a guessed list. Triggers a scrape on first call
    if the DB is still empty."""
    load_or_scrape_events()
    return jsonify({"categories": eventsdb.distinct_categories()})


@app.route("/api/refresh", methods=["POST"])
def refresh():
    """Force a fresh scrape + geocode, overwriting events.db (use
    sparingly -- hits the live De Anza site)."""
    events = load_or_scrape_events(force_refresh=True)
    return jsonify({"status": "ok", "event_count": len(events)})


@app.route("/health")
def health():
    return jsonify({"status": "ok", "last_scraped_at": eventsdb.last_scraped_at()})


if __name__ == "__main__":
    app.run(port=5001, debug=True)
