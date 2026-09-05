"""
The one place events get ranked for a student.

app.py's /api/rerank, agent.py's tool and pipeline.py each used to carry
their own copy of "call the agent, sanity-check what came back, fill in
anything it skipped, sort". The copies drifted: agent.py was missing a
post-processing step the web path had, so the same event could come back
MEDIUM on the map and LOW when you asked the conversational agent about
it. pipeline.py mutated the caller's event dictionaries in place.

All three now call rank_events(). Fixing a ranking bug means editing one
function.

On the removed keyword override
-------------------------------
The web path used to run a substring keyword list over the ranked output
and promote anything matching from LOW to MEDIUM, replacing the agent's
written reason with a fixed sentence.

That undid the project's core design decision -- that the agent reads
the raw event text and judges it, rather than a fixed rule table
assigning points (see PROJECT_LOG.md Section 6). It also duplicated a
rule the agent already has: PRIORITY_SYSTEM_PROMPT rule 5 instructs it
not to mark transfer, registration, financial aid, deadline and similar
events LOW just because they don't match the student's major.

The substring matching was also wrong in practice: the "tag" entry
(intended for UC Transfer Admission Guarantee) matched "Heritage Month",
"Main Stage", "Vintage" and "Advantage", so unrelated events were
promoted and had their explanation overwritten with text no agent wrote.

The override is gone. Rule 5 owns this behaviour.
"""

from priority_agent import build_agent_input, prioritize_events


TIER_ORDER = {
    "high": 0,
    "medium": 1,
    "low": 2,
}

VALID_TIERS = ("high", "medium", "low")

UNRANKED_REASON = (
    "Not ranked by the agent; shown as low priority by default."
)

MISSING_REASON = "No reason given by the agent."


def rank_events(
    profile: dict,
    raw_events: list[dict],
) -> list[dict]:
    """
    Rank events for one student profile.

    Returns a new list of event copies, sorted by tier then date. The
    caller's dictionaries are never modified.

    Every input event appears in the output exactly once. The model
    occasionally returns an id that doesn't exist, or omits events
    entirely; neither should make an event silently disappear from a
    student's map.
    """

    agent_input, id_lookup = build_agent_input(raw_events)

    ranked = prioritize_events(profile, agent_input)

    final_events = []
    seen_ids = set()
    unknown_ids = []

    for item in ranked if isinstance(ranked, list) else []:

        if not isinstance(item, dict) or item.get("id") not in id_lookup:
            unknown_ids.append(
                item.get("id") if isinstance(item, dict) else item
            )
            continue

        if item["id"] in seen_ids:
            # A repeated id would otherwise show the same event twice.
            continue

        seen_ids.add(item["id"])

        event = dict(id_lookup[item["id"]])

        event["tier"] = (
            item.get("tier")
            if item.get("tier") in VALID_TIERS
            else "low"
        )

        event["reason"] = item.get("reason") or MISSING_REASON

        final_events.append(event)

    if unknown_ids:
        print(
            f"[ranking] agent returned {len(unknown_ids)} "
            f"unrecognized id(s), skipped: {unknown_ids}"
        )

    dropped_ids = sorted(set(id_lookup) - seen_ids)

    if dropped_ids:
        print(
            f"[ranking] agent didn't rank {len(dropped_ids)} event(s), "
            f"added as low priority: {dropped_ids}"
        )

        for event_id in dropped_ids:
            event = dict(id_lookup[event_id])
            event["tier"] = "low"
            event["reason"] = UNRANKED_REASON
            final_events.append(event)

    final_events.sort(
        key=lambda event: (
            TIER_ORDER.get(event.get("tier"), 2),
            event.get("date") or "9999-12-31",
        )
    )

    return final_events
