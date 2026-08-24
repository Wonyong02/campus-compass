# Campus Compass

Surfaces hidden or scattered information from school websites — events,
deadlines, workshops — and consolidates it into a single map-based
interface. An AI agent (built with the [Strands Agents
SDK](https://strandsagents.com)) scores each event's importance based
on a student's profile (year, major, interests) instead of a fixed
formula, and displays the results as a prioritized map + agenda. A
student sets their profile once and the browser remembers it — no
login required.

Built for the **Agents for Humans Hackathon** (Devpost), Everyday
Agents track. See [`PROJECT_LOG.md`](./PROJECT_LOG.md) for the full
build story, design decisions, and known limitations.

## Architecture

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
                                           panel; profile lives in the
                                           browser's localStorage, no
                                           login/account)
```

Each stage in `my_agent/` is a standalone, independently-runnable
script. `pipeline.py` still exists as a way to chain scrape → geocode →
prioritize into one static JSON snapshot (useful for offline testing),
but the live app reads events from `events.db` and calls the Strands
Agent fresh on every profile change via `app.py`.

## Setup

**1. Clone this repo and create a virtual environment:**

```bash
git clone <this-repo-url>
cd campus-compass
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
```

**2. Install dependencies:**

```bash
pip install -r requirements.txt
```

This includes Flask + Flask-CORS (for the live backend) in addition to
the Strands Agents SDK and scraping libraries. SQLite itself needs no
separate install — it's part of the Python standard library.

**3. Set up AWS Bedrock access** (each teammate needs their own):

- Have an AWS account
- Submit Anthropic's one-time "use case details" form the first time you
  invoke a Claude model on Bedrock (via Bedrock → Model catalog → click
  a Claude model). Takes ~15 min to propagate.
- Create an IAM user with the `AmazonBedrockFullAccess` policy, generate
  an access key, then run:

```bash
aws configure
# Region: us-west-2 (or wherever you enabled Claude model access)
```

**Never commit your AWS access key/secret to this repo.** Each person
should configure their own local credentials via `aws configure`
(this writes to `~/.aws/credentials`, which is outside the repo).

## Usage

Start the backend (first run scrapes + geocodes De Anza's events into
`my_agent/events.db`; later runs reuse that database instead of
re-scraping):

```bash
python -u my_agent/app.py
```

This serves on `http://localhost:5001`. Then open
`my_agent/campus_map_prototype.html` in a browser. On first visit,
click "Edit profile" to set your year/major/interests and get a live,
AI-ranked map; the profile is saved to that browser's `localStorage`
and automatically re-applied on future visits — no login, no account.
If the backend isn't running, the page still displays a static
snapshot rather than failing outright.

To force a fresh scrape (bypassing the cached database), call
`POST /api/refresh`, or run the older standalone pipeline:

```bash
python -u my_agent/pipeline.py
```

(edit the `STUDENT_PROFILE` dict at the top of that file to change
which profile it personalizes for).

## Project structure

```
campus-compass/
├── README.md
├── PROJECT_LOG.md          # full build log: decisions, limitations, next steps
├── requirements.txt
└── my_agent/
    ├── agent.py             # minimal Strands agent (SDK/auth sanity check)
    ├── scrape_events.py     # scrapes De Anza College's events pages
    ├── geocode_events.py    # resolves free-text locations to lat/lng
    ├── priority_agent.py    # Strands Agent that ranks events per student
    ├── db.py                # SQLite persistence for scraped/geocoded events
    ├── app.py                # Flask backend: live re-ranking + categories API
    ├── pipeline.py          # standalone scrape→geocode→prioritize→JSON snapshot
    └── campus_map_prototype.html   # map + agenda + ticker + profile panel UI
```

## Next steps

See `PROJECT_LOG.md` §15 for the full list. Highlights:
- Notification logic (1-week / 1-day-before reminders)
- Separate Event Detail page + Filter/Search
- Support for additional schools (De Anza's scraper is school-specific)
