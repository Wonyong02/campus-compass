"""
Single source of truth for the student profile vocabulary.

The `year` and `major` values a student can pick used to be written out
by hand in five different places (the HTML form, get_year_guidance(),
the agent system prompt, agent.py's tool docstring, and pipeline.py's
example profile). They drifted: the form offered "general" while the
backend only recognised "sophomore"/"junior"/"senior", so the option
silently did nothing.

Everything that needs to know what a valid year or major is now reads it
from here, and `check_profile_vocabulary()` makes drift visible instead
of letting it fail quietly.
"""

from event_category_map import MAJOR_EVENT_CATEGORIES


# ---------------------------------------------------------
# Year
# ---------------------------------------------------------
# De Anza is a community college, not a fixed 4-year track -- students
# commonly take anywhere from about 1.5 to 3+ years -- so "year" is a
# rough self-reported stage rather than a precise count. The one clear
# signal it gives: a freshman probably hasn't been through orientation
# yet, and anyone further along almost certainly has.

YEAR_OPTIONS = [
    {
        "value": "",
        "label": "All years",
        "guidance": "neutral",
    },
    {
        "value": "freshman",
        "label": "Freshman",
        "guidance": "boost",
    },
    {
        "value": "general",
        "label": "General student",
        "guidance": "reduce",
    },
]


# The year field used to offer freshman/sophomore/junior/senior. Stored
# profiles, saved accounts and agent.py tool calls can still contain the
# old values, so they keep working instead of silently falling back to
# "neutral".
LEGACY_YEAR_ALIASES = {
    "sophomore": "general",
    "junior": "general",
    "senior": "general",
}

_YEAR_GUIDANCE = {
    option["value"]: option["guidance"]
    for option in YEAR_OPTIONS
}


def normalize_year(year: str | None) -> str:
    """Map any accepted year value onto a current YEAR_OPTIONS value."""

    value = (year or "").strip().lower()

    return LEGACY_YEAR_ALIASES.get(value, value)


def get_year_guidance(year: str | None) -> str:
    """
    Return "boost", "reduce" or "neutral" for a student's year.

    Interpreted by PRIORITY_SYSTEM_PROMPT alongside each event's
    is_orientation_event flag.
    """

    return _YEAR_GUIDANCE.get(
        normalize_year(year),
        "neutral",
    )


def describe_year_guidance() -> str:
    """
    Render the year vocabulary as prompt text.

    Generated from YEAR_OPTIONS so the system prompt cannot describe a
    set of years the form no longer offers.
    """

    lines = []

    for option in YEAR_OPTIONS:
        if not option["value"]:
            continue

        lines.append(
            f'- "{option["value"]}" ({option["label"]}) '
            f'-> year_guidance is "{option["guidance"]}"'
        )

    return "\n".join(lines)


# ---------------------------------------------------------
# Major
# ---------------------------------------------------------

MAJOR_FAMILIES = {
    "Technology / Engineering / STEM": [
        "Computer Science",
        "Data Science",
        "Cybersecurity",
        "Engineering",
        "Mathematics",
        "Physics",
    ],

    "Art / Design / Media": [
        "Art",
        "Art History",
        "Studio Art",
        "Graphic Design",
        "Photography",
        "Film / Television",
        "Music",
    ],

    "Life Science / Health": [
        "Biology",
        "Chemistry",
        "Health Sciences",
        "Nursing",
        "Public Health",
        "Kinesiology",
    ],

    "Business / Economics": [
        "Accounting",
        "Business Administration",
        "Economics",
    ],

    "Social / Behavioral Sciences": [
        "Anthropology",
        "Cognitive Science",
        "Communication Studies",
        "Global Studies",
        "Political Science",
        "Psychology",
        "Sociology",
        "Administration of Justice",
    ],

    "Humanities / Language": [
        "English",
        "History",
        "Humanities",
        "Linguistics",
        "Philosophy",
        "Journalism",
    ],

    "Environment / Earth Science": [
        "Environmental Science",
        "Geography",
        "Geology",
    ],

    "Education / Human Services": [
        "Child Development",
    ],

    "Law / Legal Studies": [
        "Paralegal Studies",
    ],
}


UNDECLARED_MAJOR = "Undeclared / Undecided"


def get_major_family(major: str | None) -> str:
    """Return the broader major family for a student's selected major."""

    if not major:
        return ""

    if major == UNDECLARED_MAJOR:
        return "Undeclared / General"

    for family, majors in MAJOR_FAMILIES.items():
        if major in majors:
            return family

    return "Other / General"


# The list the profile form offers. Derived from the mappings rather
# than typed out again in HTML, so a major can never appear in the
# dropdown without the backend knowing about it.
MAJOR_OPTIONS = sorted(
    set(MAJOR_EVENT_CATEGORIES)
    | {
        major
        for majors in MAJOR_FAMILIES.values()
        for major in majors
    }
) + [UNDECLARED_MAJOR]


# ---------------------------------------------------------
# Drift check
# ---------------------------------------------------------

def check_profile_vocabulary() -> dict[str, list[str]]:
    """
    Report majors that are offered but only partly wired up.

    A major with no entry in MAJOR_EVENT_CATEGORIES still works -- it
    just gets no De Anza category grounding, and the student sees no
    "Personalization notes" line. That is a legitimate state for
    Undeclared, but for a real major it means personalization quietly
    does less than the UI implies, which is exactly the kind of failure
    that is invisible until someone audits it.
    """

    missing_categories = [
        major
        for major in MAJOR_OPTIONS
        if major != UNDECLARED_MAJOR
        and major not in MAJOR_EVENT_CATEGORIES
    ]

    missing_family = [
        major
        for major in MAJOR_OPTIONS
        if major != UNDECLARED_MAJOR
        and get_major_family(major) == "Other / General"
    ]

    return {
        "missing_event_categories": missing_categories,
        "missing_major_family": missing_family,
    }


if __name__ == "__main__":
    print(f"{len(MAJOR_OPTIONS)} majors offered")
    print(f"{len(YEAR_OPTIONS)} year options offered\n")

    for name, majors in check_profile_vocabulary().items():
        print(f"{name}: {majors or 'none'}")
