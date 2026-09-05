"""
Central configuration for Campus Compass.

Everything that differs between a laptop and a deployed server lives
here: secrets, file paths, and runtime flags. Application modules import
from this file instead of hardcoding values, so there is exactly one
place to look when something needs to change for deployment.

Secrets are read from the environment (via a local `.env` file in
development). Nothing secret has a hardcoded fallback -- a missing
secret fails loudly at startup rather than silently running with a
value that is public on GitHub.
"""

import os
import secrets
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).parent


def _env(name: str, default: str | None = None) -> str | None:
    """
    Read an environment variable, treating an empty value as unset.

    .env files are normally created by copying .env.example, which lists
    every key with a blank value. os.getenv() reports those keys as set
    (to ""), so a plain os.getenv(name, default) would return "" and the
    default would never apply -- which silently disabled Google Sign-In
    the first time a .env existed.
    """

    value = os.getenv(name)

    return value if value else default

# Anchored to this file rather than the working directory. The server is
# normally started from the home directory (`python -u my_agent/app.py`),
# so a bare load_dotenv() would look for ~/.env and quietly miss the
# my_agent/.env sitting next to this file.
load_dotenv(BASE_DIR / ".env")

# Also honour a .env in the working directory, if there is one. Values
# already loaded above win.
load_dotenv()


# ---------------------------------------------------------
# Runtime
# ---------------------------------------------------------

# Werkzeug's debugger allows arbitrary code execution through the
# browser, so it must never be on for a deployment that is reachable by
# anyone else. Opt in explicitly via the environment instead.
DEBUG = (_env("CAMPUS_COMPASS_DEBUG") or "").lower() in ("1", "true", "yes")

PORT = int(_env("CAMPUS_COMPASS_PORT", "5001"))


# ---------------------------------------------------------
# Secrets
# ---------------------------------------------------------

def get_secret_key() -> str:
    """
    Return the Flask secret key.

    This key signs BOTH session cookies and password-reset tokens, so a
    published value means anyone can forge a reset token for any account.
    It therefore has no hardcoded default.

    In development a random key is generated per process (sessions and
    reset links stop working across restarts, which is the intended
    reminder to set the variable properly).
    """

    key = _env("FLASK_SECRET_KEY")

    if key:
        return key

    if not DEBUG:
        raise RuntimeError(
            "FLASK_SECRET_KEY is not set. Set it in the environment "
            "before running Campus Compass outside local development."
        )

    print(
        "[config] WARNING: FLASK_SECRET_KEY is not set. Using a random "
        "development key -- sessions and password reset links will not "
        "survive a restart."
    )

    return secrets.token_hex(32)


# Deliberately a function, not a module-level constant: scrape_events.py
# and priority_agent.py import this module for file paths, and a scraper
# has no business failing to start because a web secret is unset.

# A Google OAuth client ID is public by design (it ships to the browser),
# so keeping a shared default here is safe and lets teammates test Google
# Sign-In without their own .env. The client *secret* is never used by
# this flow and must not be added here.
GOOGLE_CLIENT_ID = _env(
    "GOOGLE_CLIENT_ID",
    "212453297953-pg5c31tka8nboe3f9hgctlh33rfaeanq.apps.googleusercontent.com",
)

EMAIL_SENDER = _env("CAMPUS_COMPASS_EMAIL")
EMAIL_APP_PASSWORD = _env("CAMPUS_COMPASS_EMAIL_PASSWORD")

SMTP_HOST = _env("CAMPUS_COMPASS_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(_env("CAMPUS_COMPASS_SMTP_PORT", "465"))


# ---------------------------------------------------------
# Password reset
# ---------------------------------------------------------

PASSWORD_RESET_SALT = "campus-compass-password-reset"
PASSWORD_RESET_MAX_AGE = 60 * 60


# ---------------------------------------------------------
# Paths
# ---------------------------------------------------------
# Resolved against this file's directory rather than the current working
# directory, so scripts behave the same whether they are run from the
# repository root or from inside my_agent/.

DB_PATH = BASE_DIR / "events.db"
EVENTS_JSON = BASE_DIR / "deanza_events.json"
EVENTS_GEOCODED_JSON = BASE_DIR / "deanza_events_geocoded.json"
PIPELINE_OUTPUT_JSON = BASE_DIR / "campus_events_final.json"


# ---------------------------------------------------------
# Scraping
# ---------------------------------------------------------

SCRAPE_MONTHS_AHEAD = int(_env("CAMPUS_COMPASS_MONTHS_AHEAD", "3"))
REQUEST_DELAY_SECONDS = 2
