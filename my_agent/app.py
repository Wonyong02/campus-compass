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
from priority_agent import prioritize_events

app = Flask(__name__)
CORS(app)  # the map page is opened as a local file / localhost, so allow any origin

_events_cache = None


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

    agent_input = []
    id_lookup = {}
    for i, ev in enumerate(raw_events):
        if not ev.get("title"):
            continue  # same skip-unparseable-events rule as pipeline.py
        agent_input.append({
            "id": i,
            "title": ev["title"],
            "date": ev.get("date"),
            "time": ev.get("time"),
            "location": ev.get("location"),
            "description": (ev.get("description") or "")[:300],
        })
        id_lookup[i] = ev

    try:
        ranked = prioritize_events(profile, agent_input)
    except Exception as e:  # Bedrock call failed / bad JSON back from the agent, etc.
        return jsonify({"error": f"Agent re-ranking failed: {e}"}), 502

    final_events = []
    for item in ranked:
        ev = dict(id_lookup[item["id"]])
        ev["tier"] = item["tier"]
        ev["reason"] = item["reason"]
        final_events.append(ev)

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
