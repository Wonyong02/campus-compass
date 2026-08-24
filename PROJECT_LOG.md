# Campus Compass — Project Log

**Hackathon:** Agents for Humans Hackathon (Devpost)
**Track:** Everyday Agents
**Deadline:** September 14, 2026, 5:00 PM PDT
**Built with:** Strands Agents SDK (Amazon Bedrock, Claude Sonnet 4.6)

## 1. Project Concept

Campus Compass surfaces hidden or scattered information from school
websites — events, deadlines, workshops — and consolidates it into a
single map-based interface. An AI agent scores each event's importance
based on a student's profile (year, major, interests) rather than a
fixed formula, and displays the results as a prioritized map + agenda.
Long-term, it can send reminders a week or a day before high-priority
events so students stop missing things buried across disconnected
school pages.

Hackathon submission answer (Everyday Agents track):

> I'll be building for the Everyday Agents track. My project surfaces
> hidden or scattered information from various school websites (events,
> deadlines, opportunities) and consolidates it into a single map-based
> interface. The AI will prioritize what's shown based on each student's
> profile — year, major, and interests — and can send reminders a week
> or a day before important events, so students stop missing things
> buried across dozens of disconnected school pages.

## 2. Architecture

```
scrape_events.py  --->  geocode_events.py  --->  priority_agent.py  --->  pipeline.py
(real event data)      (lat/lng lookup)         (Strands Agent          (glues it all
                                                  reasoning)              together)
                                                                              |
                                                                              v
                                                          campus_map_prototype.html
                                                          (map + agenda + ticker UI)
```

Each stage is a standalone, independently-runnable script. `pipeline.py`
imports and chains the three data-processing stages; the HTML file is a
separate visualization layer that currently consumes a hand-embedded
snapshot of `pipeline.py`'s output (see Section 8, "Known Limitations").

## 3. Environment Setup

- Python virtual environment: `python3 -m venv .venv` → `source .venv/bin/activate`
- SDK: `pip install strands-agents strands-agents-tools`
- AWS Bedrock:
  - AWS account already existed; Bedrock model access is now
    auto-enabled per-account (AWS retired the manual "Model access"
    toggle page in 2026).
  - Anthropic models required a one-time **"Submit use case details"**
    form (via Bedrock → Model catalog → click a Claude model). Took
    about 15 minutes to propagate after submission.
  - IAM: created a dedicated user, attached `AmazonBedrockFullAccess`,
    generated an access key, configured locally via `aws configure`
    (region: `us-west-2`).
- Model used: `Claude Sonnet 4.6` (via Bedrock's `US Anthropic Claude
  Sonnet 5` cross-region inference profile).

## 4. Component: Basic Agent (`agent.py`)

First working Strands agent — validated the whole toolchain (SDK,
Bedrock auth, model access) using a trivial agent with `calculator`,
`current_time`, and a custom `letter_counter` tool. This is the
"hello world" checkpoint before building anything project-specific.

## 5. Component: Map UI Prototype (`campus_map_prototype.html`, v1)

First version of the map UI, built with **mock data** before any real
scraping existed, to validate the interaction design early:

- Leaflet.js map with color/size-coded pins (red = high priority, amber
  = medium, blue = low)
- A "departure board" style ticker across the top showing today's
  top-priority items
- An agenda sidebar, sorted by priority, that flies the map to a pin on click
- Profile selector (year / major / interest chips) that recomputed
  priority live via a simple rule-based JS scoring function

Design direction: a "personal campus wayfinding kiosk" aesthetic — ink
navy header, warm paper background, coral/amber/slate priority coding,
monospace ticker text evoking an airport departure board.

## 6. Component: Priority Agent (`priority_agent.py`)

Replaced the mock JS scoring function with a real Strands Agent call.
Key design decision: rather than pre-computing tags/scores in Python
and handing the model a already-processed number, the agent receives
**raw event text** (title, description, date) plus the student profile,
and reasons about relevance and urgency itself.

This mattered concretely once real data arrived: a rigid point formula
would have scored "Financial Aid Deadline" as high priority purely from
urgency, but the agent correctly reasoned it should be *medium* for a
student whose stated interests don't include financial topics — nuance
a fixed rule set doesn't capture.

Output shape per event: `{ id, tier: "high"|"medium"|"low", reason }`.

## 7. Component: Web Scraper (`scrape_events.py`)

Target: `https://www.deanza.edu/events/` (De Anza College).

**Platform discovery:** Initially assumed this might run on Localist
(a common campus calendar SaaS with a public JSON API) — it doesn't.
De Anza runs a **custom PHP calendar system on OmniUpdate CMS**, no
public API. Scraping was the only option.

**Two different page templates had to be handled:**

| Page | Structure | Key fields |
|---|---|---|
| `/events/` (Upcoming Events list) | `<h4 class="event-title">`, `<h3 class="mb-0">` for date grouping, icon-prefixed `<p>` tags for time/location | Most detailed (has category, description) |
| `/events/month.html?m=&y=` (calendar grid) | `<td class="day">` with `<time datetime="YYYY-MM-DD">`, nested `<div class="event">` blocks | Reaches further into the future; exact ISO dates for free |

Notably, the month view's event link isn't even an `<a href>` — it's
plain text inside `<div class="link">`. Found this only by diffing raw
HTML text search against a failed CSS-selector query, a reminder that
"the substring exists in the page" and "it's reachable via the
selector you assumed" are different questions.

**Resilience added after hitting a real `403 Forbidden`:**
- Requests are spaced with `time.sleep(2)` between calls
- A blocked/failed page is skipped (logged, not fatal) — one bad month
  doesn't crash the whole scrape
- Results from both templates are merged and de-duplicated by the
  numeric event ID embedded in each detail URL

## 8. Component: Geocoding (`geocode_events.py`)

Scraped locations are free text ("Online via Zoom", "Transfer Center,
Registration & Student Services Bldg., (2nd Floor)", "Parking Lots A &
B") — not coordinates. Resolved via a static lookup table rather than
a live geocoding API (avoids requiring the user to set up and pay for
a separate Google Maps API key mid-hackathon):

- **Confirmed** coordinates (from Google Places, via `places_search`):
  De Anza College main campus, Registration & Student Services
  building, Hinson Campus Center
- **Approximate** coordinates: informal internal building nicknames
  (e.g. "Social Sciences & Humanities Village Center") aren't
  independently listed on Google Places, so these are hand-estimated
  relative to the confirmed campus center and explicitly flagged
  `match_type: "approximate"`
- **Virtual**: any location containing "online"/"zoom"/"virtual" gets
  no coordinates at all — the UI shows a badge instead of a fabricated pin
- **None**: events with no location (e.g. "Last day to add 12-week
  classes" — a deadline, not a place) correctly get `null`, rather than
  being force-fit onto a map pin

This honesty-over-completeness choice (returning `null`/`approximate`
rather than always producing *some* coordinate) carries through to the
final map UI, which visually distinguishes confirmed vs. approximate
vs. virtual vs. no-location events.

## 9. Component: Full Pipeline (`pipeline.py`)

Chains scrape → geocode → prioritize into one script. Fixed a single
student profile at the top of the file (easy to edit):

```python
STUDENT_PROFILE = {
    "year": "sophomore",
    "major": "Computer Science",
    "interests": ["career", "academic"],
}
```

Output: `campus_events_final.json` — every scraped event, enriched
with coordinates and an agent-assigned tier + reason. This file is the
single source of truth the map should ideally read from.

**Live pipeline run result (2026-08-23):** 13 real events scraped
across the "upcoming" list page and 3 months of calendar-grid pages,
spanning Aug 25 – Sep 22, 2026. All events geocoded (5 virtual, 3
confirmed/approximate physical locations, 2 with no location, correctly
left blank). Agent ranked 3 as high priority (both UC transfer
workshops + "Fall classes begin"), 6 medium, 4 low — matching manual
inspection of what's actually relevant to a CS-major sophomore.

## 10. Component: Final Map (`campus_map_prototype.html`, v2)

Rebuilt to consume real pipeline output instead of mock data:

- Mock JS scoring function removed entirely — the map now only
  *visualizes* tiers the agent already computed in Python
- Cards show the agent's actual one-sentence `reason` per event
- Virtual events get a "VIRTUAL" badge instead of a map pin
- Approximate/fallback-geocoded locations get a `~` prefix so the UI
  doesn't overclaim precision it doesn't have
- Profile selector became a **read-only banner** ("Personalized for:
  Sophomore · Computer Science...") since re-ranking now requires a
  real (non-instant) Bedrock call — see limitations below

## 11. Known Limitations / Honest Caveats

- **Profile selection is no longer live-interactive** in the HTML.
  Changing the displayed student profile now requires re-running
  `pipeline.py` (which calls the LLM) rather than an instant client-side
  recompute. Making it interactive again needs a small backend endpoint
  (e.g. Flask/FastAPI) the page can call on profile change.
- **Single data source.** Only De Anza's own events page is scraped.
  Real deployment would need per-school scraper configs, since every
  school's site structure differs (as seen firsthand: De Anza's own two
  page templates already required separate parsing logic).
- **Approximate coordinates for informal building names** aren't
  precise — a real deployment should source exact coordinates from the
  school's own campus map/GIS data instead of hand-estimating.
- **Scraping is fragile by nature.** A future redesign of De Anza's
  site would break the CSS/tag selectors used here. No monitoring/alerting
  exists yet for "the scraper silently returns 0 events."
- **Rate limiting is real.** Hit a genuine `403` from De Anza's server
  during testing from making too many requests too quickly. Current
  fix (2-second delay, skip-on-failure) is enough for a prototype, not
  necessarily enough for a scheduled production scrape.

## 12. Possible Next Steps

- [ ] Backend endpoint for live profile-based re-ranking
- [ ] Notification logic (1-week / 1-day-before reminders)
- [ ] Support additional schools / a config-driven scraper
- [ ] Deploy the agent to Bedrock AgentCore Runtime (per hackathon resources)
- [ ] Handle recurring/multi-day events more explicitly
- [ ] Real campus GIS data instead of estimated building coordinates

## 13. Hackathon Logistics

- Registered for Agents for Humans Hackathon (Devpost)
- Submitted the $50 AWS Promotional Credits request (deadline: Sep 11,
  2026, 12pm PT — separate from the Sep 14 project deadline)
- Track selected: **Everyday Agents**
