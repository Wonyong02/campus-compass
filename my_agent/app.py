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

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

import os
import smtplib
from dotenv import load_dotenv

from email.message import EmailMessage

import db as eventsdb
from scrape_events import scrape_all_events
from geocode_events import geocode_location
from priority_agent import build_agent_input, prioritize_events, get_relevant_event_categories, get_year_guidance
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv(
    "GOOGLE_CLIENT_ID",
    "212453297953-pg5c31tka8nboe3f9hgctlh33rfaeanq.apps.googleusercontent.com"
)
EMAIL_SENDER = os.getenv("CAMPUS_COMPASS_EMAIL")
EMAIL_APP_PASSWORD = os.getenv("CAMPUS_COMPASS_EMAIL_PASSWORD")


def send_email(
    to_email: str,
    subject: str,
    body: str,
) -> None:
    if not EMAIL_SENDER or not EMAIL_APP_PASSWORD:
        raise RuntimeError(
            "Email credentials are not configured."
        )

    message = EmailMessage()
    message["From"] = f"Campus Compass <{EMAIL_SENDER}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
    ) as smtp:
        smtp.login(
            EMAIL_SENDER,
            EMAIL_APP_PASSWORD,
        )

        smtp.send_message(message)

app = Flask(__name__)
app.secret_key = "campus-compass-dev-secret"

CORS(app)


password_reset_serializer = URLSafeTimedSerializer(
    app.secret_key
)

PASSWORD_RESET_SALT = "campus-compass-password-reset"
PASSWORD_RESET_MAX_AGE = 60 * 60

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

def create_password_reset_token(email: str) -> str:
    return password_reset_serializer.dumps(
        email,
        salt=PASSWORD_RESET_SALT,
    )


def read_password_reset_token(token: str) -> str | None:
    try:
        return password_reset_serializer.loads(
            token,
            salt=PASSWORD_RESET_SALT,
            max_age=PASSWORD_RESET_MAX_AGE,
        )

    except (BadSignature, SignatureExpired):
        return None

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

    profile.setdefault("year", "")
    profile.setdefault("major", "")
    profile.setdefault("interests", [])

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

    # Surface the same major -> category grounding the agent used, so the
    # frontend can show it as a read-only note instead of asking the
    # student to re-pick categories that are already derived from their
    # major (see priority_agent.py's "interests are preference signals,
    # not filters" rule -- manually selecting a category here never
    # changed the ranking).
    response_profile = dict(profile)
    response_profile["relevant_event_categories"] = get_relevant_event_categories(
        profile["major"]
    )
    # Same idea for year: surface whether orientation events are being
    # boosted/reduced for this student's year (see priority_agent.py's
    # get_year_guidance() and PRIORITY_SYSTEM_PROMPT rule 11).
    response_profile["year_guidance"] = get_year_guidance(
        profile.get("year", "")
    )

    return jsonify({
        "generated_at": datetime.now().isoformat(),
        "student_profile": response_profile,
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

@app.route("/api/config", methods=["GET"])
def public_config():
    return jsonify({
        "google_client_id": GOOGLE_CLIENT_ID or ""
    })

@app.route("/api/google-login", methods=["POST"])
def google_login():
    data = request.get_json(silent=True) or {}

    credential = str(
        data.get("credential") or ""
    ).strip()

    if not credential:
        return jsonify({
            "error": "Google credential is required."
        }), 400

    if not GOOGLE_CLIENT_ID:
        return jsonify({
            "error": "Google login is not configured."
        }), 500

    try:
        google_user = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            GOOGLE_CLIENT_ID,
        )

    except ValueError:
        return jsonify({
            "error": "Invalid Google sign-in."
        }), 401

    email = str(
        google_user.get("email") or ""
    ).strip().lower()

    email_verified = google_user.get(
        "email_verified",
        False,
    )

    if not email or not email_verified:
        return jsonify({
            "error": "Google email could not be verified."
        }), 401

    # ---------------------------------
    # Existing Campus Compass account?
    # ---------------------------------

    user = eventsdb.get_user_by_email(email)

    is_new_user = False

    # ---------------------------------
    # First Google login -> create user
    # ---------------------------------

    if not user:
        random_password = os.urandom(32).hex()

        password_hash = generate_password_hash(
            random_password
        )

        user = eventsdb.create_user(
            email=email,
            password_hash=password_hash,
            year="",
            major="",
            interests=[],
        )

        is_new_user = True

        # New Google users start with
        # Daily Event Email enabled.
        try:
            eventsdb.save_subscriber(
                email=email,
                year="",
                major="",
                interests=[],
            )

        except Exception as e:
            print(
                f"[google-login] "
                f"subscription error: {e}"
            )

    # ---------------------------------
    # Log in using the same session
    # format as normal email login
    # ---------------------------------

    session["user_id"] = user["user_id"]
    session["email"] = user["email"]

    return jsonify({
        "status": "ok",
        "message": "Signed in with Google.",
        "is_new_user": is_new_user,
        "user": {
            "user_id": user["user_id"],
            "email": user["email"],
            "year": user.get("year", ""),
            "major": user.get("major", ""),
            "interests": user.get("interests", []),
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

@app.route("/api/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}

    email = str(
        data.get("email", "")
    ).strip().lower()

    if not email:
        return jsonify({
            "status": "error",
            "message": "Enter your email address."
        }), 400

    user = eventsdb.get_user_by_email(email)

    # Do not reveal whether an account exists.
    if user:
        token = create_password_reset_token(email)

        reset_link = (
            request.host_url.rstrip("/")
            + "/?reset_token="
            + token
        )

        subject = "Reset your Campus Compass password"

        body = (
            "Hi,\n\n"
            "We received a request to reset your Campus Compass password.\n\n"
            "Use the link below to create a new password:\n\n"
            f"{reset_link}\n\n"
            "This link will expire in 1 hour.\n\n"
            "If you did not request a password reset, "
            "you can ignore this email.\n\n"
            "Campus Compass"
        )

        send_email(
            email,
            subject,
            body,
        )

    return jsonify({
        "status": "ok",
        "message": (
            "If an account exists for that email, "
            "a password reset link will be sent."
        )
    })

@app.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}

    token = str(
        data.get("token", "")
    ).strip()

    new_password = str(
        data.get("password", "")
    )

    if not token:
        return jsonify({
            "status": "error",
            "message": "Invalid password reset link."
        }), 400

    if len(new_password) < 8:
        return jsonify({
            "status": "error",
            "message": "Password must be at least 8 characters."
        }), 400

    email = read_password_reset_token(token)

    if not email:
        return jsonify({
            "status": "error",
            "message": (
                "This password reset link is invalid "
                "or has expired."
            )
        }), 400

    password_hash = generate_password_hash(
        new_password
    )

    updated = eventsdb.update_user_password(
        email,
        password_hash,
    )

    if not updated:
        return jsonify({
            "status": "error",
            "message": "Unable to reset password."
        }), 400

    return jsonify({
        "status": "ok",
        "message": "Password updated successfully."
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