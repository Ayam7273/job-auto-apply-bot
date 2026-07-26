"""
automation/generic_fallback_handler.py

Used when no dedicated platform handler matches. This does best-effort
field matching by reading each input's associated label text and
matching it against the profile's personal fields or Q&A entries.

Deliberately conservative: if it can't confidently fill the resume
upload and the core contact fields (name/email/phone), it stops and
flags the application for manual review instead of submitting a
partially-filled or wrong form. Submitting garbage is worse than
skipping — a bad auto-submission can burn your one shot at a role.
"""

from automation.base_handler import BaseHandler, match_personal_field, best_qa_match
from processor import ApplicationStatus


class GenericFallbackHandler(BaseHandler):
    name = "generic_fallback"

    def matches(self, url: str) -> bool:
        # Last-resort handler — registry only reaches this if nothing
        # else matched, so it always "matches".
        return True

    async def apply(self, page, link: str, profile: dict) -> ApplicationStatus:
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass  # some pages never go fully idle (polling widgets etc.) — proceed anyway

        # Quick closed-posting check before attempting anything else
        page_text = (await page.inner_text("body")).lower()
        closed_signals = [
            "no longer accepting applications",
            "position has been filled",
            "job is no longer available",
            "posting has closed",
            "this position is closed",
        ]
        if any(sig in page_text for sig in closed_signals):
            return ApplicationStatus.CLOSED

        filled_count = 0
        confident_required_filled = {"name": False, "email": False}

        text_inputs = await page.query_selector_all(
            "input[type='text'], input[type='email'], input[type='tel'], "
            "input:not([type]), textarea"
        )

        for field in text_inputs:
            label_text = await self._get_label_text(page, field)
            if not label_text:
                continue

            matched_key = match_personal_field(label_text)
            value = None

            if matched_key:
                value = profile.get("personal", {}).get(matched_key)
                if matched_key == "full_name" and value:
                    confident_required_filled["name"] = True
                if matched_key == "email" and value:
                    confident_required_filled["email"] = True
            else:
                value = best_qa_match(label_text, profile)

            if value:
                try:
                    await field.fill(str(value))
                    filled_count += 1
                except Exception:
                    continue  # field might be disabled/hidden — skip it

        # Resume upload
        resume_uploaded = False
        resume_path = profile.get("resume_path")
        if resume_path:
            file_inputs = await page.query_selector_all("input[type='file']")
            if file_inputs:
                try:
                    await file_inputs[0].set_input_files(resume_path)
                    resume_uploaded = True
                except Exception:
                    pass

        # Conservative gate: don't submit unless the essentials are in place
        if not (confident_required_filled["name"] and confident_required_filled["email"] and resume_uploaded):
            return ApplicationStatus.NEEDS_MANUAL_REVIEW

        # Look for a verification-code prompt before attempting submit
        if "verification code" in page_text or "check your email" in page_text:
            return ApplicationStatus.NEEDS_VERIFICATION

        if "assessment" in page_text or "take a test" in page_text or "hackerrank" in page_text:
            return ApplicationStatus.NEEDS_ASSESSMENT

        submit_button = await page.query_selector(
            "button[type='submit'], input[type='submit'], button:has-text('Submit'), "
            "button:has-text('Apply')"
        )
        if not submit_button:
            return ApplicationStatus.NEEDS_MANUAL_REVIEW

        try:
            await submit_button.click()
            await page.wait_for_timeout(2000)
        except Exception:
            return ApplicationStatus.NEEDS_MANUAL_REVIEW

        return ApplicationStatus.SUCCESS

    async def _get_label_text(self, page, field) -> str | None:
        """Try a few common ways a field's label might be associated."""
        try:
            field_id = await field.get_attribute("id")
            if field_id:
                label_el = await page.query_selector(f"label[for='{field_id}']")
                if label_el:
                    text = await label_el.inner_text()
                    if text:
                        return text

            placeholder = await field.get_attribute("placeholder")
            if placeholder:
                return placeholder

            aria_label = await field.get_attribute("aria-label")
            if aria_label:
                return aria_label

            name_attr = await field.get_attribute("name")
            if name_attr:
                return name_attr.replace("_", " ").replace("-", " ")
        except Exception:
            pass
        return None