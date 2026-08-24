"""
Small Flask backend that makes the student profile live again.

Why this exists: pipeline.py bakes ONE hardcoded STUDENT_PROFILE into
campus_events_final.json, and the map just visualizes that snapshot.
Changing the profile used to mean editing pipeline.py and re-running it
by hand (see PROJECT_LOG.md, section 11). This server exposes the same
re-ranking step (geocode_events -> priority_agent) as an HTTP endpoint,
so campus_map_prototype.html's profile panel can call it live instead.

Scraping is left OUT of the per-request path on purpose -- De Anza's
server gets rate-limited fast (see PROJECT_LOG.md, section 7), and the
scrape doesn't change when a student's profile changes. So:
  - Events are scraped + geocoded ONCE (cached to deanza_events_geocoded.json)
  - Every /api/rerank call only re-runs the Strands Agent's priority
    judgment against that cached event list, for whatever profile was
    posted. That's genuinely fast and safe to call on every profile edit.
  - POST /api/refresh forces a fresh scrape if you want up-to-date events
    (use sparingly -- it hits the live De Anza site).

Run:
    pip install -r requirements.txt
    python my_agent/app.py
Serves on http://localhost:5001
"""
import json
import os
from datetime import datetime

from flask import Flask, jsonify, request
from flask_cors import CORS

from scrape_events import scrape_all_events
from geocode_events import geocode_location
from priority_agent import prioritize_events

app = Flask(__name__)
CORS(app)  # the map page is opened as a local file / localhost, so allow any origin

CACHE_FILE = os.path.join(os.path.dirname(__file__), "deanza_events_geocoded.json")

_events_cache = None


def load_or_scrape_events(force_refresh: bool = False) -> list[dict]:
    """Returns the scraped+geocoded event list, using a local JSON cache
    so we don't hit De Anza's server on every profile change."""
    global _events_cache

    if _events_cache is not None and not force_refresh:
        return _events_cache

    if not force_refresh and os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as f:
            _events_cache = json.load(f)
        return _events_cache

    print("Scraping + geocoding fresh De Anza events (hits the live site, please be patient)...")
    raw_events = scrape_all_events(months_ahead=3)
    for ev in raw_events:
        ev.update(geocode_location(ev.get("location")))

    with open(CACHE_FILE, "w") as f:
        json.dump(raw_events, f, indent=2)

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


@app.route("/api/refresh", methods=["POST"])
def refresh():
    """Force a fresh scrape + geocode (use sparingly -- hits the live site)."""
    events = load_or_scrape_events(force_refresh=True)
    return jsonify({"status": "ok", "event_count": len(events)})


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    app.run(port=5001, debug=True)
