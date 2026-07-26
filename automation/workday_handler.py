"""
automation/workday_handler.py

Workday careers sites are all the same underlying product (Workday
HCM), just re-skinned per employer — so unlike custom career pages,
the FLOW is genuinely consistent across companies even though this
still needs live calibration (Workday updates their UI periodically,
and some tenants customize field sets).

Typical flow:
  1. Job posting page -> "Apply Manually" (avoid "Autofill with Resume"
     for now — it requires an existing session/account in some tenants).
  2. Create Account / Sign In (email + password).
  3. "My Information" step — name, contact, resume upload.
  4. "My Experience" step — work history, education (often skippable
     if resume was parsed).
  5. "Application Questions" step — work authorization, sponsorship,
     custom yes/no and text questions -> answered via profile Q&A.
  6. "Voluntary Disclosures" / self-identification — left as default
     ("decline to answer") deliberately; this is sensitive personal
     data and shouldn't be auto-filled from guesses.
  7. "Review" -> Submit.

Uses Playwright's semantic locators (get_by_role/get_by_label) over
raw CSS where possible — these tend to survive Workday's periodic UI
updates better than guessing at `data-automation-id` values.
"""

import logging

from automation.base_handler import BaseHandler, best_qa_match, get_account_password
from processor import ApplicationStatus

logger = logging.getLogger(__name__)

CLOSED_SIGNALS = [
    "no longer accepting applications",
    "position has been filled",
    "this job is no longer available",
    "posting has closed",
]

# Password is now sourced from the profile (see automation/base_handler.py's
# get_account_password) — fixed and memorable by design, not derived/random.


class WorkdayHandler(BaseHandler):
    name = "workday"

    def matches(self, url: str) -> bool:
        return "myworkdayjobs.com" in url

    async def apply(self, page, link: str, profile: dict) -> ApplicationStatus:
        try:
            # Workday is a heavy JS app — domcontentloaded fires before the
            # actual page content (buttons, forms) has rendered. Give it
            # time to settle before looking for anything.
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                await page.wait_for_timeout(3000)  # fallback if it never goes idle

            body_text = (await page.inner_text("body")).lower()
            if any(sig in body_text for sig in CLOSED_SIGNALS):
                return ApplicationStatus.CLOSED

            if not await self._start_application(page):
                return ApplicationStatus.NEEDS_MANUAL_REVIEW

            if not await self._create_account_or_sign_in(page, profile):
                return ApplicationStatus.NEEDS_MANUAL_REVIEW

            sign_in_retries = 0

            # Step through the wizard: My Information -> ... -> Review
            for _ in range(8):  # hard cap so a stuck loop can't hang forever
                # Sign-in prompts can reappear at any point (e.g. some tenants
                # re-prompt right after account creation to confirm the new
                # credentials). Handle it wherever it shows up, using the
                # same deterministic password — no need to "remember" it,
                # it's regenerated from the profile email every time.
                if await self._is_stuck_on_signin(page):
                    sign_in_retries += 1
                    if sign_in_retries > 2:
                        return ApplicationStatus.NEEDS_MANUAL_REVIEW
                    if not await self._attempt_sign_in(page, profile):
                        return ApplicationStatus.NEEDS_MANUAL_REVIEW
                    continue  # re-check the (hopefully new) page from the top

                body_text = (await page.inner_text("body")).lower()

                if "verification code" in body_text or "check your email" in body_text:
                    return ApplicationStatus.NEEDS_VERIFICATION

                if "assessment" in body_text or "hackerrank" in body_text or "codility" in body_text:
                    return ApplicationStatus.NEEDS_ASSESSMENT

                await self._fill_my_information(page, profile)
                await self._fill_application_questions(page, profile)

                if await self._is_review_step(page):
                    break

                if not await self._click_next(page):
                    break  # no more Next button — assume we're done or stuck

            submitted = await self._submit(page)
            return ApplicationStatus.SUCCESS if submitted else ApplicationStatus.NEEDS_MANUAL_REVIEW

        except Exception as e:
            logger.exception("Workday handler failed for %s: %s", link, e)
            return ApplicationStatus.ERROR

    # ---- step helpers ----

    async def _start_application(self, page) -> bool:
        # Some tenants show "Apply Manually" directly on the job page.
        try:
            await page.get_by_role("button", name="Apply Manually", exact=False).first.click(timeout=4000)
            await page.wait_for_timeout(1500)
            return True
        except Exception:
            pass

        # Others show a plain "Apply" button that opens a modal with
        # Autofill with Resume / Apply Manually / Use My Last Application.
        # exact=True matters here — "Apply" with exact=False would also
        # match "Apply Manually" and "Autofill with Resume" as substrings.
        try:
            await page.get_by_role("button", name="Apply", exact=True).first.click(timeout=6000)
            await page.wait_for_timeout(1000)
        except Exception:
            return False

        try:
            await page.get_by_role("button", name="Apply Manually", exact=False).first.click(timeout=6000)
            await page.wait_for_timeout(1500)
            return True
        except Exception:
            return False

    async def _is_stuck_on_signin(self, page) -> bool:
        try:
            body_text = (await page.inner_text("body")).lower()
            return "sign in" in body_text and "password" in body_text
        except Exception:
            return False

    async def _attempt_sign_in(self, page, profile: dict) -> bool:
        """Fills email + the deterministic password and submits Sign In.
        Safe to call any time a sign-in screen is detected, whether it's
        the first prompt or a re-prompt after account creation."""
        email = profile.get("personal", {}).get("email", "")
        if not email:
            return False
        password = get_account_password(profile)

        try:
            try:
                await page.get_by_label("Email Address", exact=False).first.fill(email, timeout=5000)
            except Exception:
                await page.get_by_label("Email", exact=True).first.fill(email, timeout=5000)

            await page.get_by_label("Password", exact=False).first.fill(password, timeout=5000)
            await page.get_by_role("button", name="Sign In", exact=False).first.click(timeout=5000)
            await page.wait_for_timeout(2000)
        except Exception:
            return False

        return not await self._is_stuck_on_signin(page)

    async def _create_account_or_sign_in(self, page, profile: dict) -> bool:
        email = profile.get("personal", {}).get("email", "")
        if not email:
            return False
        password = get_account_password(profile)

        # This is always a brand-new profile applying for the first time,
        # so we always want Create Account, never Sign In. Some tenants
        # default to showing a Sign In form with a "Create Account" link
        # underneath — switch to that mode first if so.
        try:
            body_text = (await page.inner_text("body")).lower()
            if "sign in" in body_text and "create account" in body_text:
                try:
                    await page.get_by_text("Create Account", exact=False).first.click(timeout=4000)
                    await page.wait_for_timeout(1000)
                except Exception:
                    pass  # might already be on the create-account form
        except Exception:
            pass

        try:
            await page.get_by_label("Email", exact=True).first.fill(email, timeout=8000)
        except Exception:
            try:
                await page.get_by_label("Email Address", exact=False).first.fill(email, timeout=5000)
            except Exception:
                pass

        try:
            pw_fields = page.get_by_label("Password", exact=False)
            count = await pw_fields.count()
            for i in range(count):
                await pw_fields.nth(i).fill(password, timeout=5000)
        except Exception:
            pass

        try:
            await page.get_by_label("I Agree", exact=False).first.check(timeout=3000)
        except Exception:
            pass  # not all tenants have a terms checkbox

        clicked = False
        for label in ["Create Account", "Sign In"]:
            try:
                await page.get_by_role("button", name=label, exact=False).first.click(timeout=5000)
                clicked = True
                await page.wait_for_timeout(2000)
                break
            except Exception:
                continue

        if not clicked:
            return False

        # Verify we actually moved past auth — don't just assume the click worked.
        try:
            still_stuck = await page.get_by_role("heading", name="Sign In", exact=False).first.is_visible(
                timeout=3000
            )
            if still_stuck:
                return False
        except Exception:
            pass  # heading not found at all = good, we've moved on

        return True

    async def _fill_my_information(self, page, profile: dict) -> None:
        personal = profile.get("personal", {})
        field_map = {
            "First Name": personal.get("full_name", "").split(" ")[0] if personal.get("full_name") else "",
            "Last Name": " ".join(personal.get("full_name", "").split(" ")[1:]) if personal.get("full_name") else "",
            "Email": personal.get("email", ""),
            "Phone Number": personal.get("phone", ""),
            "Address": personal.get("location", ""),
        }
        for label, value in field_map.items():
            if not value:
                continue
            try:
                target = page.get_by_label(label, exact=False)
                # "Address" matches "Email Address" too as a substring —
                # skip any match whose full label mentions email, since
                # that's a different field entirely.
                if label == "Address":
                    count = await target.count()
                    filled = False
                    for i in range(count):
                        candidate = target.nth(i)
                        try:
                            acc_name = (await candidate.get_attribute("aria-label")) or ""
                        except Exception:
                            acc_name = ""
                        if "email" in acc_name.lower():
                            continue
                        await candidate.fill(value, timeout=5000)
                        filled = True
                        break
                    if not filled and count > 0:
                        continue  # only email-labeled match found — skip rather than risk it
                else:
                    await target.first.fill(value, timeout=5000)
            except Exception:
                continue

        # Resume upload
        resume_path = profile.get("resume_path")
        if resume_path:
            try:
                await page.locator("input[type='file']").first.set_input_files(resume_path, timeout=5000)
                await page.wait_for_timeout(1500)
            except Exception:
                pass

    async def _fill_application_questions(self, page, profile: dict) -> None:
        try:
            await page.wait_for_timeout(1000)  # let the step's fields render
            questions = await page.query_selector_all("fieldset, [role='group']")
            for q in questions:
                try:
                    label_text = await q.inner_text()
                except Exception:
                    continue
                if not label_text:
                    continue

                answer = best_qa_match(label_text.split("\n")[0], profile)
                if not answer:
                    continue

                # Try radio/button choice matching the answer text first
                option = await q.query_selector(f"text='{answer}'")
                if option:
                    try:
                        await option.click()
                        continue
                    except Exception:
                        pass

                # Fall back to a text input inside this question block
                text_input = await q.query_selector("input[type='text'], textarea")
                if text_input:
                    try:
                        await text_input.fill(str(answer))
                    except Exception:
                        pass
        except Exception:
            pass

    async def _is_review_step(self, page) -> bool:
        try:
            await page.get_by_role("heading", name="Review", exact=False).first.wait_for(
                state="visible", timeout=3000
            )
            return True
        except Exception:
            return False

    async def _click_next(self, page) -> bool:
        for label in ["Save and Continue", "Next"]:
            try:
                await page.get_by_role("button", name=label, exact=False).first.click(timeout=6000)
                await page.wait_for_timeout(1500)
                return True
            except Exception:
                continue
        return False

    async def _submit(self, page) -> bool:
        try:
            await page.get_by_role("button", name="Submit", exact=False).first.click(timeout=6000)
            await page.wait_for_timeout(2000)
            return True
        except Exception:
            return False