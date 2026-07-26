"""
platform_detector.py

First pass at figuring out what kind of job posting a link points to.

Right now this only does URL/domain-level detection. Once we know your
real ATS mix (from the 200-300 links), this gets extended with actual
per-platform handlers in automation/.

LinkedIn / Indeed handling:
  - If the link is a LinkedIn or Indeed URL, we flag it specially.
  - Real behavior (once Playwright is wired in) will be:
      1. Open the page.
      2. If a "manual apply" / "apply on company site" option exists
         alongside Easy Apply, use that path instead.
      3. If ONLY Easy Apply is available, flag as unavailable rather
         than risk the account.
  - For now (pre-Playwright), we can only do the URL-level flag below;
    the "does it also offer manual apply" check needs to inspect the
    actual page.
"""

from enum import Enum
from urllib.parse import urlparse


class Platform(Enum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    ICIMS = "icims"
    SMARTRECRUITERS = "smartrecruiters"
    LINKEDIN = "linkedin"
    INDEED = "indeed"
    UNKNOWN = "unknown"


# Domain fragments mapped to platform. Extend this as we learn your real mix.
DOMAIN_SIGNATURES = {
    "greenhouse.io": Platform.GREENHOUSE,
    "boards.greenhouse.io": Platform.GREENHOUSE,
    "jobs.lever.co": Platform.LEVER,
    "myworkdayjobs.com": Platform.WORKDAY,
    "icims.com": Platform.ICIMS,
    "smartrecruiters.com": Platform.SMARTRECRUITERS,
    "linkedin.com": Platform.LINKEDIN,
    "indeed.com": Platform.INDEED,
}


def detect_platform(link: str) -> Platform:
    domain = urlparse(link).netloc.lower()
    for signature, platform in DOMAIN_SIGNATURES.items():
        if signature in domain:
            return platform
    return Platform.UNKNOWN


def is_easy_apply_only_risk(platform: Platform) -> bool:
    """
    True if this platform is one where we should NOT blindly auto-apply
    (LinkedIn Easy Apply / Indeed Easy Apply risk account bans), and
    instead need to check for a manual-apply alternative first.
    """
    return platform in (Platform.LINKEDIN, Platform.INDEED)
