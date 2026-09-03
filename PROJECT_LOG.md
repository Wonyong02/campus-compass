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
scrape_events.py  --->  geocode_events.py  --->  db.py (SQLite)
(real event data)      (lat/lng lookup)         (events.db, persisted
                                                   so scraping only runs
                                                   once, not per request)
                                                        |
                                                        v
                                                    app.py (Flask)
                                                    POST /api/rerank  ---> priority_agent.py
                                                    GET  /api/categories    (Strands Agent
                                                    POST /api/refresh        reasoning, computed
                                                    GET  /health              live per profile)
                                                        |
                                                        v
                                          campus_map_prototype.html
                                          (map + agenda + ticker + profile
                                           panel; profile itself lives in
                                           the browser's localStorage, no
                                           login/account)
```

Scraping, geocoding, and storage are decoupled from the AI judgment
step on purpose: the event data doesn't change when a student's profile
changes, but the priority *does*, so only `priority_agent.py`'s work is
re-run on every profile edit. `pipeline.py` still exists as a standalone
script that chains scrape → geocode → prioritize → static JSON snapshot,
useful for offline testing without the Flask server running.

*(As of Section 18 below, this diagram is incomplete: `app.py` now also
serves the frontend directly and exposes auth/subscription endpoints,
and `agent.py` is a second, conversational entry point into the same
event data.)*

## 3. Environment Setup

- Python virtual environment: `python3 -m venv .venv` → `source .venv/bin/activate`
- SDK: `pip install strands-agents strands-agents-tools`
- Backend: `pip install flask flask-cors` (added when the live
  re-ranking API was built; see Section 11)
- Database: `sqlite3` — Python standard library, no extra install
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

*(Superseded 2026-09-02 — see Section 18.6: the demo tools were replaced
with a real Campus Compass tool that reads from `events.db`.)*

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

*(Extended 2026-08-28 — see Section 17.6: the agent now also receives
De Anza event-category grounding alongside major/interests.)*

## 7. Component: Web Scraper (`scrape_events.py`)

Target: `https://deanza.edu/events/` (De Anza College). *(Base URL
changed from `www.deanza.edu` to non-`www` on 2026-08-28 — see Section
17.3; `www` was returning a 403.)*

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

*(Extended 2026-08-28 — a third page type, `/events/category.html?c=...`,
was added. See Section 17.2.)*

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
with coordinates and an agent-assigned tier + reason. This is still
useful as an offline snapshot / demo fallback, but `events.db` (Section
12) is now the actual source of truth the live backend reads from.

**Live pipeline run result (2026-08-23):** 13 real events scraped
across the "upcoming" list page and 3 months of calendar-grid pages,
spanning Aug 25 – Sep 22, 2026. All events geocoded (5 virtual, 3
confirmed/approximate physical locations, 2 with no location, correctly
left blank). Agent ranked 3 as high priority (both UC transfer
workshops + "Fall classes begin"), 6 medium, 4 low — matching manual
inspection of what's actually relevant to a CS-major sophomore.

## 10. Component: Static Map Snapshot (`campus_map_prototype.html`, v2)

Rebuilt to consume real pipeline output instead of mock data:

- Mock JS scoring function removed entirely — the map now only
  *visualizes* tiers the agent already computed in Python
- Cards show the agent's actual one-sentence `reason` per event
- Virtual events get a "VIRTUAL" badge instead of a map pin
- Approximate/fallback-geocoded locations get a `~` prefix so the UI
  doesn't overclaim precision it doesn't have
- Profile selector became a **read-only banner** ("Personalized for:
  Sophomore · Computer Science...") since re-ranking at this stage
  required re-running `pipeline.py` by hand — this limitation is what
  Section 11 below replaces.

## 11. Component: Live Profile Re-ranking Backend (`app.py`)

Replaced the read-only banner with a real Flask API so the profile
panel can call `priority_agent.py` on demand instead of requiring a
manual `pipeline.py` re-run:

- `POST /api/rerank` — body `{ year, major, interests }`, returns
  freshly-ranked events (`tier` + `reason` per event) for that exact
  profile, computed live against the Strands Agent
- `GET /api/categories` — real category labels seen in the scraped
  events, so the profile panel offers actual De Anza categories instead
  of a guessed list
- `POST /api/refresh` — forces a fresh scrape + geocode, overwriting
  the stored event list (used sparingly — hits the live De Anza site)
- `GET /health` — status + last-scraped timestamp

Scraping and geocoding are deliberately kept **out of** the
`/api/rerank` request path: De Anza's server rate-limits aggressively
(see Section 7), and the event list doesn't change when a student's
profile changes. Only the Strands Agent's judgment re-runs per request;
the underlying event data is read from `events.db` (Section 12).

End-to-end verified locally with real Bedrock calls (e.g. a
junior/transfer-focused profile correctly re-ranked transfer-related
workshops as high priority). A single `/api/rerank` call takes roughly
6 seconds in practice — genuine Bedrock/Strands Agent latency, not a
bug — which shaped both the database design (avoid re-scraping on that
critical path) and the frontend UX (Section 13's loading indicator).

*(Extended 2026-09-02 — `app.py` gained auth/subscription endpoints and
now serves the frontend directly. See Section 18.)*

## 12. Component: Event Database (`db.py`, SQLite) + No-Login Profile Persistence

**Product direction (explicit decision):** rather than building account
/ login functionality next, the goal is for a student to get full map
personalization just by setting their year/major/interests once — no
account required. Concretely: SQLite over Supabase for the database (no
external service to provision for a hackathon-scale dataset), and the
student's profile lives entirely in the browser's `localStorage`
instead of a server-side user table.

*(Updated 2026-09-02 — see Section 18.3–18.4: `users` and
`subscribers` tables were added, and account-based login now exists
alongside the original localStorage-only flow.)*

**`events.db` (SQLite) stores:**
- One `events` table: scraped + geocoded event data (title, date, time,
  location, category, description, url, coordinates, virtual flag,
  match_type, scraped_at)
- A full refresh (`save_events`) wipes and re-inserts on every scrape —
  the dataset is small (a few dozen events) and always comes from one
  fresh scrape, so no incremental upsert logic is needed

**Deliberately NOT in the database (as of 2026-08-24):**
- `tier` / `reason` — these are computed **per student profile** by
  `priority_agent.py` on every `/api/rerank` call, not an intrinsic
  property of an event. Persisting them would mean the next student
  with a different profile sees priorities computed for someone else.
- `Users` / `Preferences` / `SavedEvents` tables — intentionally absent
  under the no-login direction above. *(A `users` table and account-linked
  profile storage were added in Section 18.3–18.4.)*

**Frontend (`campus_map_prototype.html`) changes:**
- `localStorage` key `campusCompassProfile` stores `{ year, major,
  interests }` on the browser that set it
- On page load, if a saved profile exists, the page automatically calls
  `/api/rerank` with it and re-renders — no re-entering the profile on
  every visit
- `GET /api/categories` populates the interest chip list with real
  category labels instead of a hardcoded guess

## 13. Bug Fix: Profile Chip UI Race Condition

Shortly after shipping Section 12, a real bug surfaced: after a page
refresh, the profile banner correctly restored the saved profile, but
the "Edit profile" panel's interest chips still showed the *default*
selection (career/academic) instead of the actual saved interests —
the two were out of sync.

**Root cause:** page load fires two async calls at once — the fast
`GET /api/categories` (~9ms) and the slow `POST /api/rerank` (~6s, real
Bedrock latency). The chip-rendering function preferred whatever was
already lit up in the DOM over the live profile state, so the fast
call's render (still showing defaults, since the slow call hadn't
resolved yet) got "preserved" even after the slow call finally restored
the correct profile.

**Fix:** chip rendering now only trusts DOM state once the student has
actually clicked a chip themselves in that page load (tracked via a
`userEditedInterests` flag); otherwise it always derives from the live
profile object. Also added a "Personalizing your map for your saved
profile…" banner state while the ~6-second auto-restore call is in
flight, so the wait doesn't read as broken/reverted.

Verified with an automated jsdom test that reproduces the exact race
(fast `/api/categories` resolving before slow `/api/rerank`) before
shipping.

## 14. Known Limitations / Honest Caveats

- **Login is optional, not required.** A student's profile can still
  live only in the browser that set it (localStorage), so nothing is
  gated behind an account. Signing up (Section 18.3) additionally syncs
  the profile and email notification preference to that account.
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
- **Single-page frontend.** Map, agenda, ticker, and profile panel all
  live in one HTML file rather than separate Home/Events/Detail pages.
  *(As of 9/2, auth/signup panels were added to this same file too.)*
- **Flask's dev server is single-threaded**, and a `/api/rerank` call
  takes several real seconds (Bedrock latency) — acceptable for a
  hackathon demo, not production-grade concurrency.

## 15. Possible Next Steps

- [x] ~~Backend endpoint for live profile-based re-ranking~~ — done, see Section 11
- [x] ~~Minimal database~~ — done (SQLite), see Section 12
- [x] ~~Major-based personalization / category grounding~~ — done, see Section 17
- [x] ~~Map marker grouping for co-located events~~ — done, see Section 18.1
- [ ] **Actual email delivery** — subscription storage exists (Section
      18.2) but sending is not implemented yet. Closest to the
      hackathon track's stated emphasis ("only ping you when there's a
      real decision to make")
- [ ] 1-week / 1-day-before reminder logic (builds on the above)
- [ ] Separate Event Detail page + Filter/Search
- [ ] Support additional schools / a config-driven scraper
- [ ] Deploy the agent to Bedrock AgentCore Runtime (per hackathon resources)
- [ ] Handle recurring/multi-day events more explicitly
- [ ] Real campus GIS data instead of estimated building coordinates
- [ ] User Flow documentation / page-structure diagram

## 16. Hackathon Logistics

- Registered for Agents for Humans Hackathon (Devpost)
- Submitted the $50 AWS Promotional Credits request (deadline: Sep 11,
  2026, 12pm PT — separate from the Sep 14 project deadline)
- Track selected: **Everyday Agents**

## 17. Major-Based Event Personalization (2026-08-28)

**Goal:** the major selector already existed, but the agent had no
grounded data connecting a given major to which De Anza event
categories actually matter for it.

### 17.1 New file: `event_category_map.py`

Maps 25+ majors to relevant De Anza event categories (e.g. Computer
Science / Data Science → "Business, Computer Science and Applied
Technologies" + "Physical Sciences, Mathematics and Engineering";
Biology / Health Sciences → "Biological, Health and Environmental
Sciences"; Art / Graphic Design / Photography → "Creative Arts").
Also defines a `GENERAL_EVENT_CATEGORIES` list that applies regardless
of major (Career Training, Student Clubs and Organizations, Student
Services and Resources, Transfer University Representative, Transfer
Workshop).

**Design principle: category is a relevance signal, not a strict
filter.** An event outside a student's mapped categories is never
hidden outright.

### 17.2 Category-aware scraping

Added `/events/category.html?c=...` as a third scrape target alongside
the existing `/events/` and `/events/month.html` pages (Section 7).
Category pages are scraped first so that when the same event exists in
multiple sources, the category-tagged version wins during
de-duplication by event ID.

### 17.3 Fixed a real `403` on the `www` subdomain

`https://www.deanza.edu/...` returned `403 Forbidden`; the bare
`https://deanza.edu/...` domain worked. The scraper's base URL was
changed to non-`www`.

### 17.4 Handled HTML structure differences on category pages

Some category pages don't use the `h4.event-title` / `h3.mb-0`
selectors the main event page uses (plain `h4`/`h3` instead), which
silently produced 0 results (e.g. "Student Services and Resources" —
Welcome Day was on the page but not found). Added a fallback selector
path, and stopped discarding an event entirely just because one
expected container wasn't found.

### 17.5 Live scrape verification (2026-08-28)

**52 unique events** collected. Category distribution: `None` 39,
Transfer University Representative 9, Transfer Workshop 4, Student
Services and Resources 1. The high `None` count is expected — month/
general list pages don't carry category metadata; the agent still
judges those events from title/description/date/major/urgency.

### 17.6 Category grounding wired into `priority_agent.py`

Each event now carries a `category` field; each student profile now
also carries `major_family`, `relevant_event_categories`, and
`general_event_categories`. System-prompt rules: exact major match =
strong signal, major-family match = related-field signal, De Anza
category match = grounding signal (**not** an automatic HIGH),
transfer/registration/academic-deadline events can be important
regardless of major, and events with no category are still judged from
their content.

**Verified end-to-end:** the same real event ("San Jose State
University Business Info Session") returned `MEDIUM` for a Computer
Science profile ("less relevant to CS but covers transfer options")
and `HIGH` for a Business Administration profile ("directly matches
Business Administration major") via `/api/rerank` — confirming the
same event now produces different, profile-appropriate priorities.

### 17.7 GitHub

- Branch: `major-data-personalization`
- Commit: "Add major-based event personalization with De Anza
  categories" (touching `event_category_map.py`, `priority_agent.py`,
  `scrape_events.py`)
- Merged to `main` via PR

## 18. Map Marker Grouping, Email Subscription, and User Authentication (2026-09-02)

### 18.1 Map marker grouping

Events sharing the same coordinates previously rendered as overlapping
pins. Co-located events are now grouped into a single marker; the
marker shows a count and, on click, a popup lists every event at that
location. Marker color is driven by the highest-priority event in the
group.

### 18.2 Email notification subscription (infrastructure only)

- New `subscribers` SQLite table
- Backend endpoints to subscribe/unsubscribe from daily event email
- A "Daily Event Email" section added to the profile panel; email
  address stored in `localStorage`; subscription-status UI added
- A logged-in user's account email is used automatically for
  notifications (the email field becomes read-only while logged in)
- **Actual email delivery is not implemented yet** — this section
  covers storage and UI only. See Section 15 for the follow-up.

### 18.3 User authentication

- New `users` SQLite table; passwords stored hashed
- `POST /api/signup`, `POST /api/login`, `POST /api/logout`,
  `GET /api/me` (session restore) added
- Flask session support so login persists across page refreshes
- **The frontend is now served directly by Flask** at
  `http://localhost:5001` (rather than opened as a static file) so
  sessions work correctly

### 18.4 User profile persistence tied to accounts

- Year/major/interests are now connected to user accounts
- Editing the profile via "Update priorities" while logged in saves to
  the account; saved profile is restored automatically after login or
  page refresh

### 18.5 Authentication UI

- Sign up / Log in buttons, an auth panel for email/password input,
  frontend integration with the signup/login APIs, logged-in email
  display, and a Log out button
- "Edit profile" button given a stronger accent color for visibility

### 18.6 Strands Agent (`agent.py`) updated

Replaced the original calculator / current-time / letter-counter demo
tools (Section 4) with a Campus-Compass-specific Strands tool that
loads real events from `events.db` and reuses the existing
personalization/priority logic. The agent can now retrieve and
summarize a student's personalized upcoming De Anza events
conversationally, not just via the `/api/rerank` REST path.

### 18.7 Current status

- Signup/login work; login persists after refresh; profiles are stored
  and restored correctly; subscription info can be stored
- Co-located map events are handled correctly
- **Actual daily email delivery has not been implemented yet**

### 18.8 GitHub

- Commit: `b668636` — "Add user auth, email subscription, and event
  improvements"
- Branch: `major-data-personalization` (same branch continued from
  Section 17), merged to `main` via PR #3
- `requirements.txt` unchanged by this commit — no new Python
  dependency was declared for hashing/sessions/email despite the
  feature scope; worth double-checking `app.py`'s imports match what's
  actually installed
