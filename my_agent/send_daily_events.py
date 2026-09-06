from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from html import escape
import sys

import db as eventsdb
from email_service import send_email
from ranking import rank_events
import config


MAX_EVENTS = 5


def get_student_profile(email, subscriber):
    """
    Build the best available profile for Daily Events.

    Prefer the logged-in user's latest profile field by field.
    If a field is empty, fall back to the subscriber profile.
    """

    user = eventsdb.get_user_by_email(email) or {}
    subscriber = subscriber or {}

    year = (
        user.get("year")
        or subscriber.get("year")
        or ""
    )

    major = (
        user.get("major")
        or subscriber.get("major")
        or ""
    )

    user_interests = user.get("interests") or []
    subscriber_interests = subscriber.get("interests") or []

    interests = (
        user_interests
        if user_interests
        else subscriber_interests
    )

    return {
        "year": year,
        "major": major,
        "interests": interests,
    }

def get_recommended_events(profile):
    """
    Return personalized events for the rest of the current week.

    Rules:
    1. Use Campus Compass's configured timezone.
    2. Exclude events before today.
    3. Exclude events after this Sunday.
    4. Rank only this week's remaining events.
    5. Today's events always appear before later events.
    """

    raw_events = eventsdb.load_events()

    if not raw_events:
        raise RuntimeError(
            "No events are stored in the database. "
            "Open Campus Compass or refresh events first."
        )

    timezone = ZoneInfo(
        config.DAILY_EMAIL_TIMEZONE
    )

    today = datetime.now(
        timezone
    ).date()

    # Python weekday:
    # Monday = 0, Sunday = 6
    week_start = today - timedelta(
        days=today.weekday()
    )

    week_end = week_start + timedelta(
        days=6
    )

    weekly_events = []

    for event in raw_events:
        event_date_text = (
            event.get("date")
            or ""
        ).strip()

        if not event_date_text:
            continue

        try:
            event_date = datetime.strptime(
                event_date_text[:10],
                "%Y-%m-%d",
            ).date()

        except ValueError:
            continue

        # Do not send events that already happened.
        if event_date < today:
            continue

        # Only events in the current Mon-Sun week.
        if event_date > week_end:
            continue

        weekly_events.append(event)

    if not weekly_events:
        return []

    # Let the existing AI ranking system rank
    # only the relevant events from this week.
    ranked_events = rank_events(
        profile,
        weekly_events,
    )

    today_iso = today.isoformat()

    # Stable sort:
    # today's events first.
    # Inside each group, preserve the AI ranking order.
    ranked_events.sort(
        key=lambda event: (
            0
            if event.get("date") == today_iso
            else 1
        )
    )

    return ranked_events[:MAX_EVENTS]


def build_email(events, profile):
    """
    Build HTML + plain text versions of the Daily Events email.
    """

    today = date.today().strftime("%B %d, %Y")

    major = profile.get("major") or "All majors"
    year = profile.get("year") or "All students"

    html_cards = []
    text_cards = []

    timezone = ZoneInfo(
        config.DAILY_EMAIL_TIMEZONE
    )

    today_iso = datetime.now(
        timezone
    ).date().isoformat()

    for event in events:
        is_today = (
            str(event.get("date") or "")[:10]
            == today_iso
        )
        today_label = (
            '<p style="font-weight:bold; margin-bottom:6px;">'
            'TODAY'
            '</p>'
            if is_today
            else ""
        )
        title = escape(
            str(event.get("title") or "Untitled event")
        )

        event_date = escape(
            str(event.get("date") or "Date TBA")
        )

        event_time = escape(
            str(event.get("time") or "Time TBA")
        )

        location = escape(
            str(event.get("location") or "Location TBA")
        )

        reason = escape(
            str(event.get("reason") or "")
        )

        tier = escape(
            str(event.get("tier") or "").upper()
        )

        url = str(
            event.get("url") or ""
        ).strip()

        link_html = ""

        if url.startswith(("http://", "https://")):
            safe_url = escape(
                url,
                quote=True,
            )

            link_html = (
                f'<p><a href="{safe_url}">'
                "View event details"
                "</a></p>"
            )

        html_cards.append(
            f"""
            <div style="
                margin: 20px 0;
                padding: 18px;
                border: 1px solid #dddddd;
                border-radius: 10px;
            ">
                {today_label}

                <h3 style="margin-top: 0;">
                    {title}
                    
                </h3>

                <p>
                    <strong>{event_date}</strong><br>
                    {event_time}<br>
                    {location}
                </p>

                <p>
                    <strong>Priority:</strong> {tier}
                </p>

                <p>
                    {reason}
                </p>

                {link_html}
            </div>
            """
        )

        text_cards.append(
            "\n".join([
                title,
                f"Date: {event_date}",
                f"Time: {event_time}",
                f"Location: {location}",
                f"Priority: {tier}",
                f"Why this may matter: {reason}",
                f"Details: {url}" if url else "",
            ])
        )

    html_content = f"""
    <div style="
        max-width: 650px;
        margin: auto;
        font-family: Arial, sans-serif;
        line-height: 1.5;
    ">
        <h1>Campus Compass</h1>

        <h2>Your Daily Events</h2>

        <p>{today}</p>

        <p>
            Here are today's personalized
            De Anza event recommendations.
        </p>

        <p style="color: #666666;">
            Profile: {escape(major)} · {escape(year)}
        </p>

        {''.join(html_cards)}

        <hr>

        <p style="
            color: #777777;
            font-size: 12px;
        ">
            You are receiving this email because
            Daily Event Email is enabled in Campus Compass.
            You can turn it off from Campus Compass.
        </p>
    </div>
    """

    text_content = (
        "Campus Compass - Your Daily Events\n"
        f"{today}\n\n"
        + "\n\n--------------------\n\n".join(text_cards)
        + "\n\n"
        "You are receiving this email because "
        "Daily Event Email is enabled in Campus Compass."
    )

    return html_content, text_content


def send_daily_events_to_one(email):
    email = email.strip().lower()

    subscriber = eventsdb.get_subscriber(email)

    if not subscriber:
        raise RuntimeError(
            f"{email} is not subscribed to Daily Events."
        )

    if not subscriber.get("notifications_enabled"):
        raise RuntimeError(
            f"Daily Events are turned off for {email}."
        )

    profile = get_student_profile(
        email,
        subscriber,
    )

    print(
        f"[daily-email] Ranking events for {email}..."
    )

    events = get_recommended_events(profile)

    if not events:
        raise RuntimeError(
            "No events are available to send."
        )

    html_content, text_content = build_email(
        events,
        profile,
    )

    subject = (
        f"Campus Compass Daily Events - "
        f"{date.today().strftime('%b %d')}"
    )

    result = send_email(
        email,
        subject,
        html_content,
        text_content,
    )

    print(
        f"[daily-email] Sent {len(events)} events to {email}"
    )

    return result


def send_daily_events_to_all():
    """
    Send the Daily Events email to every subscriber
    whose notifications are currently enabled.
    """

    subscribers = eventsdb.load_active_subscribers()

    if not subscribers:
        print("[daily-email] No active subscribers.")
        return {
            "total": 0,
            "sent": 0,
            "failed": 0,
        }

    total = len(subscribers)
    sent = 0
    failed = 0

    print(
        f"[daily-email] Found {total} active subscriber(s)."
    )

    for index, subscriber in enumerate(
        subscribers,
        start=1,
    ):
        email = (
            subscriber.get("email")
            or ""
        ).strip().lower()

        if not email:
            failed += 1
            print(
                f"[daily-email] [{index}/{total}] "
                "Skipped subscriber with no email."
            )
            continue

        print(
            f"[daily-email] [{index}/{total}] "
            f"Sending to {email}..."
        )

        try:
            send_daily_events_to_one(email)

            sent += 1

        except Exception as e:
            failed += 1

            print(
                f"[daily-email] [{index}/{total}] "
                f"FAILED for {email}: {e}"
            )

    print()
    print("[daily-email] Finished.")
    print(f"[daily-email] Total:  {total}")
    print(f"[daily-email] Sent:   {sent}")
    print(f"[daily-email] Failed: {failed}")

    return {
        "total": total,
        "sent": sent,
        "failed": failed,
    }

if __name__ == "__main__":

    if len(sys.argv) != 2:
        print(
            "Usage:\n"
            "  One subscriber:\n"
            "    python -u my_agent/send_daily_events.py "
            "student@example.com\n\n"
            "  All active subscribers:\n"
            "    python -u my_agent/send_daily_events.py --all"
        )

        raise SystemExit(1)

    target = sys.argv[1].strip()

    if target == "--all":
        result = send_daily_events_to_all()

    else:
        result = send_daily_events_to_one(
            target
        )

    print(result)