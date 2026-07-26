"""
automation/base_handler.py

Every platform handler (Workday, Greenhouse, etc.) implements this
interface. The registry (registry.py) picks the right handler for a
link and calls apply().

Handlers receive a live Playwright `page` already navigated to the
job link, plus the active `profile` dict (see profiles.py).
"""

from abc import ABC, abstractmethod
from difflib import SequenceMatcher

from processor import ApplicationStatus


class BaseHandler(ABC):
    """Subclass this for each ATS platform."""

    name: str = "base"

    @abstractmethod
    def matches(self, url: str) -> bool:
        """Return True if this handler should process the given URL."""
        raise NotImplementedError

    @abstractmethod
    async def apply(self, page, link: str, profile: dict) -> ApplicationStatus:
        """
        Drive the Playwright `page` through the application flow.
        Must return an ApplicationStatus. Should not raise — catch
        internally and return ApplicationStatus.ERROR on unexpected
        failures so one bad link doesn't kill the batch.
        """
        raise NotImplementedError


def get_account_password(profile: dict) -> str:
    """
    The one password used to create/sign into accounts on any ATS that
    requires one. Fixed and memorable by design — the person applying
    wants to be able to log back into any of these manually later.
    Every handler (current and future) should call this rather than
    generating or deriving its own.
    """
    return profile.get("personal", {}).get("password") or "RemoteJob2024!"


def best_qa_match(question_text: str, profile: dict, threshold: float = 0.6):
    """
    Fuzzy-match a form's question label against the profile's stored
    Q&A pairs. Returns the answer string, or None if nothing crosses
    the similarity threshold.
    """
    question_text = question_text.strip().lower()
    best_answer = None
    best_score = 0.0

    for qa in profile.get("qa", []):
        score = SequenceMatcher(None, question_text, qa["question"].strip().lower()).ratio()
        if score > best_score:
            best_score = score
            best_answer = qa["answer"]

    if best_score >= threshold:
        return best_answer
    return None


# Common field-label synonyms used by the generic fallback (and useful
# for platform handlers too, when a form has a nonstandard label).
FIELD_SYNONYMS = {
    "full_name": ["full name", "name", "your name", "legal name"],
    "email": ["email", "email address", "e-mail"],
    "phone": ["phone", "phone number", "mobile", "telephone"],
    "location": ["location", "city", "current location", "address"],
    "linkedin_url": ["linkedin", "linkedin profile", "linkedin url"],
    "portfolio_url": ["portfolio", "website", "portfolio url", "personal website"],
}


def match_personal_field(label_text: str) -> str | None:
    """Given a form field's label text, return the matching profile
    'personal' key (e.g. 'email'), or None if no confident match."""
    label = label_text.strip().lower()
    for field, synonyms in FIELD_SYNONYMS.items():
        for syn in synonyms:
            if syn in label:
                return field
    return None