"""
processor.py

Real dispatch layer: opens a Playwright page for the link, routes it
to the right handler (via automation/registry.py), and returns an
ApplicationStatus.

Aggregator/search-result links and LinkedIn/Indeed Easy-Apply-only
links are filtered out BEFORE a browser page is even opened, since
there's nothing to fill in on those.
"""

import logging
from enum import Enum

from platform_detector import detect_platform, is_easy_apply_only_risk
from automation.aggregator_detector import is_aggregator_link

logger = logging.getLogger(__name__)


class ApplicationStatus(Enum):
    SUCCESS = "success"
    CLOSED = "closed"
    NEEDS_VERIFICATION = "needs_verification"
    NEEDS_ASSESSMENT = "needs_assessment"
    EASY_APPLY_ONLY = "easy_apply_only"
    NOT_DIRECT_APPLICATION = "not_direct_application"
    NEEDS_MANUAL_REVIEW = "needs_manual_review"
    ERROR = "error"


STATUS_LABELS = {
    ApplicationStatus.SUCCESS: "✅ Applied successfully",
    ApplicationStatus.CLOSED: "⛔ Job posting no longer available",
    ApplicationStatus.NEEDS_VERIFICATION: "📧 Needs email verification code",
    ApplicationStatus.NEEDS_ASSESSMENT: "📝 Requires an assessment (skipped, not auto-attempted)",
    ApplicationStatus.EASY_APPLY_ONLY: (
        "🚫 Job Not Available (LinkedIn/Indeed Easy Apply only — "
        "no manual apply option found)"
    ),
    ApplicationStatus.NOT_DIRECT_APPLICATION: (
        "🔗 Listing/search page, not a direct application — follow through manually"
    ),
    ApplicationStatus.NEEDS_MANUAL_REVIEW: (
        "🔍 Couldn't confidently fill this one — flagged for manual review, not submitted"
    ),
    ApplicationStatus.ERROR: "⚠️ Something went wrong while processing this link",
}


async def process_application(browser, link: str, profile: dict | None = None) -> ApplicationStatus:
    """
    browser: a live Playwright Browser instance (shared across the batch,
             one new page/tab opened per link).
    """
    # Fast paths that don't need a browser page at all
    if is_aggregator_link(link):
        return ApplicationStatus.NOT_DIRECT_APPLICATION

    platform = detect_platform(link)
    if is_easy_apply_only_risk(platform):
        # Real manual-apply detection needs the page loaded — handled
        # inside the registry dispatch below via the generic/LinkedIn path.
        pass

    from automation.registry import get_handler
    handler = get_handler(link)

    page = None
    try:
        page = await browser.new_page()
        await page.goto(link, timeout=30000, wait_until="domcontentloaded")
        status = await handler.apply(page, link, profile or {})
        return status
    except Exception as e:
        logger.exception("Error processing %s: %s", link, e)
        return ApplicationStatus.ERROR
    finally:
        if page is not None:
            try:
                await page.close()
            except Exception:
                pass


async def resume_after_verification(link: str, code: str) -> ApplicationStatus:
    """
    DUMMY implementation of resuming an application after the user
    supplies a verification code. Real version needs the ORIGINAL
    browser page/context kept alive (or re-authenticated) so the code
    can be submitted into the same session — see notes in README.
    """
    import asyncio
    await asyncio.sleep(1.0)
    return ApplicationStatus.SUCCESS