# Campus Compass

Surfaces hidden or scattered information from school websites — events,
deadlines, workshops — and consolidates it into a single map-based
interface. An AI agent (built with the [Strands Agents
SDK](https://strandsagents.com)) scores each event's importance based
on a student's profile (year, major, interests) instead of a fixed
formula, and displays the results as a prioritized map + agenda.

Built for the **Agents for Humans Hackathon** (Devpost), Everyday
Agents track. See [`PROJECT_LOG.md`](./PROJECT_LOG.md) for the full
build story, design decisions, and known limitations.

## Architecture

```
scrape_events.py  --->  geocode_events.py  --->  priority_agent.py  --->  pipeline.py
(real event data)      (lat/lng lookup)         (Strands Agent          (glues it all
                                                  reasoning)              together)
                                                                              |
                                                                              v
                                                          campus_map_prototype.html
                                                          (map + agenda + ticker UI)
```

Each stage in `my_agent/` is a standalone, independently-runnable
script. `pipeline.py` chains the three data-processing stages together
and writes `campus_events_final.json`.

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

Run the full pipeline (scrape → geocode → prioritize):

```bash
python -u my_agent/pipeline.py
```

This produces `my_agent/campus_events_final.json`. Open
`my_agent/campus_map_prototype.html` in a browser to view the map —
note that it currently reads from a **hand-embedded snapshot** of the
pipeline's output rather than fetching the JSON file live (see
`PROJECT_LOG.md` §11 for why, and what it'd take to change that).

To edit which student profile the pipeline personalizes for, change the
`STUDENT_PROFILE` dict at the top of `my_agent/pipeline.py`.

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
    ├── pipeline.py          # runs all three stages end to end
    └── campus_map_prototype.html   # map + agenda + ticker UI
```

## Next steps

See `PROJECT_LOG.md` §12 for the full list. Highlights:
- Backend endpoint so the map's profile selector can re-rank live
- 1-week / 1-day-before notification logic
- Support for additional schools (De Anza's scraper is school-specific)
