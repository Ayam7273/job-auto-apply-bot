"""
automation/registry.py

Central dispatch: given a link, decide which handler processes it.
Order matters — more specific handlers must be checked before the
generic fallback, which matches everything and must stay last.

Add new platform handlers here as they're built.
"""

from automation.workday_handler import WorkdayHandler
from automation.generic_fallback_handler import GenericFallbackHandler

HANDLERS = [
    WorkdayHandler(),
    # Next up: GreenhouseHandler(), ICIMSHandler(), ...
    GenericFallbackHandler(),  # must stay last — matches everything
]


def get_handler(link: str):
    for handler in HANDLERS:
        if handler.matches(link):
            return handler
    return HANDLERS[-1]  # safety net, shouldn't be reached
