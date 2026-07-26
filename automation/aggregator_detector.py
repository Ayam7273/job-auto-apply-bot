"""
automation/aggregator_detector.py

Some links (Glassdoor, Indeed search results, Google job listings,
Talentify, etc.) are listing/search pages, not application forms.
There's nothing to fill in on these — the bot should flag them
rather than try (and fail) to find a form that isn't there.

This is pure URL logic, no browser needed, so it's fully real (not
dummy) from the start.
"""

from urllib.parse import urlparse

AGGREGATOR_DOMAINS = [
    "glassdoor.com",
    "google.com",
    "talentify.io",
    "simplyhired.com",
    "virtualvocations.com",
    "remotejobs.org",
    "jobleads.com",
    "bestjobtool.com",
    "vaia.com",
]


def is_aggregator_link(link: str) -> bool:
    domain = urlparse(link).netloc.lower()
    return any(agg in domain for agg in AGGREGATOR_DOMAINS)
