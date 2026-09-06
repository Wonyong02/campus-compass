import requests

try:
    from . import config
except ImportError:
    import config


BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def send_email(to_email, subject, html_content, text_content=None):
    """Send an email through the Brevo API."""

    if not config.BREVO_API_KEY:
        raise RuntimeError(
            "BREVO_API_KEY is not set. Add it to my_agent/.env."
        )

    payload = {
        "sender": {
            "name": config.BREVO_SENDER_NAME,
            "email": config.BREVO_SENDER_EMAIL,
        },
        "to": [
            {
                "email": to_email,
            }
        ],
        "subject": subject,
        "htmlContent": html_content,
    }

    if text_content:
        payload["textContent"] = text_content

    headers = {
        "accept": "application/json",
        "api-key": config.BREVO_API_KEY,
        "content-type": "application/json",
    }

    response = requests.post(
        BREVO_API_URL,
        json=payload,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()

    return response.json()

def sync_brevo_contact(email):
    """
    Create the user as a Brevo contact.
    If the contact already exists, keep/update it instead.
    """

    if not config.BREVO_API_KEY:
        raise RuntimeError(
            "BREVO_API_KEY is not set."
        )

    email = email.strip().lower()

    url = "https://api.brevo.com/v3/contacts"

    headers = {
        "accept": "application/json",
        "api-key": config.BREVO_API_KEY,
        "content-type": "application/json",
    }

    payload = {
        "email": email,
        "emailBlacklisted": False,
        "updateEnabled": True,
    }

    response = requests.post(
        url,
        json=payload,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()

    if response.content:
        return response.json()

    return {
        "status": "ok"
    }

