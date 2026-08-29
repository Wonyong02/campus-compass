# event_category_map.py

# De Anza event category pages that are useful for students.
# We do NOT scrape employee-only categories because they are not useful
# for the student-facing Campus Compass experience.

CATEGORY_SOURCES = {
    "Business, Computer Science and Applied Technologies":
        "https://deanza.edu/events/category.html?c=203912",

    "Physical Sciences, Mathematics and Engineering":
        "https://deanza.edu/events/category.html?c=203918",

    "Biological, Health and Environmental Sciences":
        "https://deanza.edu/events/category.html?c=203911",

    "Creative Arts":
        "https://deanza.edu/events/category.html?c=203913",

    "Social Sciences and Humanities":
        "https://deanza.edu/events/category.html?c=203919",

    "Language Arts":
        "https://deanza.edu/events/category.html?c=203915",

    "Intercultural/International Studies":
        "https://deanza.edu/events/category.html?c=203914",

    "Career Training":
        "https://deanza.edu/events/category.html?c=313038",

    "Student Clubs and Organizations":
        "https://deanza.edu/events/category.html?c=196562",

    "Student Services and Resources":
        "https://deanza.edu/events/category.html?c=205547",

    "Transfer University Representative":
        "https://deanza.edu/events/category.html?c=203928",

    "Transfer Workshop":
        "https://deanza.edu/events/category.html?c=203907",
}


# This is the "base data" that tells the system which De Anza
# event categories are relevant to each major.
MAJOR_EVENT_CATEGORIES = {
    "Computer Science": [
        "Business, Computer Science and Applied Technologies",
        "Physical Sciences, Mathematics and Engineering",
    ],

    "Data Science": [
        "Business, Computer Science and Applied Technologies",
        "Physical Sciences, Mathematics and Engineering",
    ],

    "Cybersecurity": [
        "Business, Computer Science and Applied Technologies",
    ],

    "Engineering": [
        "Physical Sciences, Mathematics and Engineering",
        "Business, Computer Science and Applied Technologies",
    ],

    "Mathematics": [
        "Physical Sciences, Mathematics and Engineering",
    ],

    "Physics": [
        "Physical Sciences, Mathematics and Engineering",
    ],

    "Chemistry": [
        "Physical Sciences, Mathematics and Engineering",
        "Biological, Health and Environmental Sciences",
    ],

    "Biology": [
        "Biological, Health and Environmental Sciences",
    ],

    "Health Sciences": [
        "Biological, Health and Environmental Sciences",
    ],

    "Nursing": [
        "Biological, Health and Environmental Sciences",
    ],

    "Public Health": [
        "Biological, Health and Environmental Sciences",
    ],

    "Kinesiology": [
        "Biological, Health and Environmental Sciences",
    ],

    "Environmental Science": [
        "Biological, Health and Environmental Sciences",
        "Physical Sciences, Mathematics and Engineering",
    ],

    "Art": [
        "Creative Arts",
    ],

    "Art History": [
        "Creative Arts",
    ],

    "Studio Art": [
        "Creative Arts",
    ],

    "Graphic Design": [
        "Creative Arts",
    ],

    "Photography": [
        "Creative Arts",
    ],

    "Film / Television": [
        "Creative Arts",
    ],

    "Music": [
        "Creative Arts",
    ],

    "Accounting": [
        "Business, Computer Science and Applied Technologies",
    ],

    "Business Administration": [
        "Business, Computer Science and Applied Technologies",
    ],

    "Economics": [
        "Social Sciences and Humanities",
        "Business, Computer Science and Applied Technologies",
    ],

    "Psychology": [
        "Social Sciences and Humanities",
    ],

    "Sociology": [
        "Social Sciences and Humanities",
    ],

    "Political Science": [
        "Social Sciences and Humanities",
    ],

    "Anthropology": [
        "Social Sciences and Humanities",
    ],

    "Administration of Justice": [
        "Social Sciences and Humanities",
    ],

    "History": [
        "Social Sciences and Humanities",
    ],

    "Philosophy": [
        "Social Sciences and Humanities",
    ],

    "English": [
        "Language Arts",
    ],

    "Journalism": [
        "Language Arts",
    ],
}


# These are useful regardless of major.
GENERAL_EVENT_CATEGORIES = [
    "Career Training",
    "Student Clubs and Organizations",
    "Student Services and Resources",
    "Transfer University Representative",
    "Transfer Workshop",
]