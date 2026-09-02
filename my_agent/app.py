"""
Flask backend for Campus Compass.

Main responsibilities:

1. Live profile re-ranking (POST /api/rerank)
2. SQLite-backed De Anza event storage
3. Email notification subscriptions

No account/login is required. Students can use the personalized map
without an account and optionally subscribe to daily event emails.
"""

import re
from datetime import datetime

from flask import Flask, jsonify, request, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from pathlib import Path

import db as eventsdb
from scrape_events import scrape_all_events
from geocode_events import geocode_location
from priority_agent import build_agent_input, prioritize_events


app = Flask(__name__)
app.secret_key = "campus-compass-dev-secret"

CORS(app)

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


EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


# =========================================================
# GENERAL EVENT HELPERS
# =========================================================

def is_generally_important_event(event: dict) -> bool:
    text = " ".join([
        event.get("title") or "",
        event.get("description") or "",
    ]).lower()

    return any(
        keyword in text
        for keyword in GENERAL_IMPORTANT_KEYWORDS
    )


def load_or_scrape_events(
    force_refresh: bool = False
) -> list[dict]:

    """
    Return scraped + geocoded events.

    Events are cached in memory and backed by SQLite so the
    De Anza website is not scraped on every request.
    """

    global _events_cache

    if _events_cache is not None and not force_refresh:
        return _events_cache

    if not force_refresh:
        cached = eventsdb.load_events()

        if cached is not None:
            _events_cache = cached
            return _events_cache

    print(
        "Scraping + geocoding fresh De Anza events "
        "(hits the live site, please be patient)..."
    )

    raw_events = scrape_all_events(months_ahead=3)

    for ev in raw_events:
        ev.update(
            geocode_location(
                ev.get("location")
            )
        )

    eventsdb.save_events(
        raw_events,
        scraped_at=datetime.now().isoformat(),
    )

    _events_cache = raw_events

    return _events_cache


# =========================================================
# EVENT RERANKING
# =========================================================

@app.route("/")
def home():
    return send_from_directory(
        Path(__file__).parent,
        "campus_map_prototype.html"
    )

@app.route("/api/rerank", methods=["POST"])
def rerank():

    """
    Body:

    {
        "year": "...",
        "major": "...",
        "interests": ["...", "..."]
    }

    Re-ranks stored De Anza events for the student's profile.
    """

    profile = request.get_json(force=True) or {}

    if not profile.get("year") or not profile.get("major"):
        return jsonify({
            "error": "year and major are required"
        }), 400

    profile.setdefault(
        "interests",
        []
    )

    if "email" in session:
        eventsdb.update_user_profile(
            email=session["email"],
            year=profile["year"],
            major=profile["major"],
            interests=profile["interests"],
        )

    raw_events = load_or_scrape_events()

    agent_input, id_lookup = build_agent_input(
        raw_events
    )

    try:
        ranked = prioritize_events(
            profile,
            agent_input,
        )

    except Exception as e:
        return jsonify({
            "error": f"Agent re-ranking failed: {e}"
        }), 502


    final_events = []

    seen_ids = set()

    skipped_ids = []


    for item in ranked if isinstance(ranked, list) else []:

        if (
            not isinstance(item, dict)
            or item.get("id") not in id_lookup
        ):
            skipped_ids.append(
                item.get("id")
                if isinstance(item, dict)
                else item
            )

            continue


        seen_ids.add(
            item["id"]
        )


        ev = dict(
            id_lookup[
                item["id"]
            ]
        )


        ev["tier"] = (
            item.get("tier")
            if item.get("tier")
            in (
                "high",
                "medium",
                "low",
            )
            else "low"
        )


        ev["reason"] = (
            item.get("reason")
            or "No reason given by the agent."
        )


        if (
            ev["tier"] == "low"
            and is_generally_important_event(ev)
        ):

            ev["tier"] = "medium"

            ev["reason"] = (
                "Broadly useful student information "
                "regardless of major."
            )


        final_events.append(ev)


    if skipped_ids:

        print(
            f"[rerank] agent returned "
            f"{len(skipped_ids)} unrecognized id(s), "
            f"skipped: {skipped_ids}"
        )


    dropped_ids = sorted(
        set(id_lookup) - seen_ids
    )


    if dropped_ids:

        print(
            f"[rerank] agent didn't rank "
            f"{len(dropped_ids)} event(s), "
            f"added as low priority: "
            f"{dropped_ids}"
        )


        for i in dropped_ids:

            ev = dict(
                id_lookup[i]
            )


            if is_generally_important_event(ev):

                ev["tier"] = "medium"

                ev["reason"] = (
                    "Broadly useful student information "
                    "regardless of major."
                )

            else:

                ev["tier"] = "low"

                ev["reason"] = (
                    "Not ranked by the agent; "
                    "shown as low priority by default."
                )


            final_events.append(ev)


    tier_order = {
        "high": 0,
        "medium": 1,
        "low": 2,
    }


    final_events.sort(
        key=lambda ev: tier_order.get(
            ev.get("tier"),
            2,
        )
    )


    return jsonify({
        "generated_at": datetime.now().isoformat(),
        "student_profile": profile,
        "events": final_events,
    })


@app.route("/api/signup", methods=["POST"])
def signup():
    data = request.get_json(force=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    year = (data.get("year") or "").strip()
    major = (data.get("major") or "").strip()
    interests = data.get("interests") or []

    if not email:
        return jsonify({"error": "Email is required."}), 400

    if len(password) < 8:
        return jsonify({
            "error": "Password must be at least 8 characters."
        }), 400

    if eventsdb.get_user_by_email(email):
        return jsonify({
            "error": "An account with this email already exists."
        }), 409

    password_hash = generate_password_hash(password)

    user = eventsdb.create_user(
        email=email,
        password_hash=password_hash,
        year=year,
        major=major,
        interests=interests,
    )

    return jsonify({
        "status": "ok",
        "message": "Account created successfully.",
        "user": user,
    })

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({
            "error": "Email and password are required."
        }), 400

    user = eventsdb.get_user_by_email(email)

    if not user:
        return jsonify({
            "error": "Invalid email or password."
        }), 401

    if not check_password_hash(user["password_hash"], password):
        return jsonify({
            "error": "Invalid email or password."
        }), 401

    session["user_id"] = user["user_id"]
    session["email"] = user["email"]

    return jsonify({
        "status": "ok",
        "message": "Logged in successfully.",
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "year": user["year"],
            "major": user["major"],
            "interests": user["interests"],
        },
    })

@app.route("/api/me", methods=["GET"])
def me():
    if "user_id" not in session:
        return jsonify({
            "logged_in": False
        })

    user = eventsdb.get_user_by_email(session["email"])

    if not user:
        session.clear()
        return jsonify({
            "logged_in": False
        })

    return jsonify({
        "logged_in": True,
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "year": user["year"],
            "major": user["major"],
            "interests": user["interests"],
        }
    })


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "status": "ok",
        "message": "Logged out successfully."
    })

# =========================================================
# EMAIL SUBSCRIPTIONS
# =========================================================

@app.route("/api/subscribe", methods=["POST"])
def subscribe():

    """
    Subscribe a student to Campus Compass daily event emails.

    Body:

    {
        "email": "student@example.com",
        "year": "sophomore",
        "major": "Computer Science",
        "interests": ["Transfer", "Career"]
    }
    """

    data = request.get_json(
        force=True
    ) or {}


    email = (
        data.get("email")
        or ""
    ).strip().lower()


    year = (
        data.get("year")
        or ""
    ).strip()


    major = (
        data.get("major")
        or ""
    ).strip()


    interests = (
        data.get("interests")
        or []
    )


    # -------------------------
    # Validate email
    # -------------------------

    if not EMAIL_PATTERN.match(email):

        return jsonify({
            "error": "Please enter a valid email address."
        }), 400


    # -------------------------
    # Profile is required
    # so emails can be personalized
    # -------------------------

    if not year:

        return jsonify({
            "error": "Year is required."
        }), 400


    if not major:

        return jsonify({
            "error": "Major is required."
        }), 400


    if not isinstance(interests, list):

        return jsonify({
            "error": "Interests must be a list."
        }), 400


    try:

        eventsdb.save_subscriber(
            email=email,
            year=year,
            major=major,
            interests=interests,
        )

    except Exception as e:

        print(
            f"[subscribe] database error: {e}"
        )

        return jsonify({
            "error": "Could not save subscription."
        }), 500


    print(
        f"[subscribe] subscribed: {email}"
    )


    return jsonify({
        "status": "ok",
        "message": "Subscribed successfully.",
        "email": email,
    })


@app.route("/api/unsubscribe", methods=["POST"])
def unsubscribe():

    """
    Disable daily email notifications.

    Body:

    {
        "email": "student@example.com"
    }
    """

    data = request.get_json(
        force=True
    ) or {}


    email = (
        data.get("email")
        or ""
    ).strip().lower()


    if not EMAIL_PATTERN.match(email):

        return jsonify({
            "error": "Please enter a valid email address."
        }), 400


    try:

        eventsdb.unsubscribe(
            email
        )

    except Exception as e:

        print(
            f"[unsubscribe] database error: {e}"
        )

        return jsonify({
            "error": "Could not unsubscribe."
        }), 500


    print(
        f"[unsubscribe] unsubscribed: {email}"
    )


    return jsonify({
        "status": "ok",
        "message": "Email notifications disabled.",
        "email": email,
    })


# =========================================================
# EVENT CATEGORIES
# =========================================================

@app.route("/api/categories", methods=["GET"])
def categories():

    """
    Return category labels actually found
    in scraped De Anza events.
    """

    load_or_scrape_events()

    return jsonify({
        "categories":
            eventsdb.distinct_categories()
    })


# =========================================================
# REFRESH EVENTS
# =========================================================

@app.route("/api/refresh", methods=["POST"])
def refresh():

    """
    Force a fresh De Anza scrape and geocode.
    """

    events = load_or_scrape_events(
        force_refresh=True
    )

    return jsonify({
        "status": "ok",
        "event_count": len(events),
    })


# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health")
def health():

    return jsonify({
        "status": "ok",
        "last_scraped_at":
            eventsdb.last_scraped_at(),
    })


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":

    app.run(
        port=5001,
        debug=True,
    )