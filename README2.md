# Job Application Bot

## Stage 3: Real automation begins

What changed:

- **Playwright is wired in for real.** `processor.py` now launches an
  actual browser page per link instead of returning random dummy
  statuses.
- **Plugin architecture** (`automation/`) — each ATS platform is a
  self-contained handler implementing `matches(url)` and
  `apply(page, link, profile)`. `automation/registry.py` picks the
  right one per link; unmatched links fall through to the generic
  handler.
- **Aggregator detector** (fully real, no browser needed) — flags
  Glassdoor/Google/Talentify/etc. listing pages as
  "not a direct application" instead of trying to fill a form that
  isn't there.
- **Generic fallback handler** (real, Playwright-based) — best-effort
  field matching by label text for any unrecognized custom career
  page. Deliberately conservative: won't submit unless it confidently
  filled name, email, and resume — otherwise flags
  `NEEDS_MANUAL_REVIEW` rather than risk a bad submission.
- **Workday handler** (real, first ATS-specific handler) — drives the
  standard multi-step Workday apply flow (Apply Manually → account →
  My Information → Application Questions → Review → Submit). Workday
  is one vendor's product reused per employer, so the flow is
  consistent — but this still needs live calibration against real
  postings (see below).

## ⚠️ Before running for real

```bash
pip install -r requirements.txt
playwright install chromium
```

The `playwright install` step downloads the actual browser binary —
easy to forget, and the bot will fail to launch a browser without it.

## Setup

Same as before — `.env` with `TELEGRAM_BOT_TOKEN`, then:
```bash
python bot.py
```

## What's real vs. still needs work

| Piece | Status |
|---|---|
| Aggregator detection | ✅ Real |
| Generic fallback (custom career pages) | ✅ Real, needs live testing to tune confidence gates |
| Workday handler | ✅ Real, needs live calibration (see below) |
| LinkedIn/Indeed manual-apply detection | 🔲 Still simplified — currently only catches the URL, doesn't yet inspect the page for a manual-apply alternative |
| Verification code resume (`resume_after_verification`) | 🔲 Still dummy — real version needs the original browser session kept alive so the code can be submitted into it |
| Greenhouse, iCIMS, and everything else | 🔲 Not built yet — falls through to the generic handler for now |

## ⚠️ Why Workday needs live calibration

I don't have live network access to job sites from where this code
was written, so the Workday handler is built from well-known Workday
UI patterns, not verified against a currently-running posting. Likely
things to check/fix once you run it against a real link:

- Exact button label text for "Apply Manually" (varies slightly by
  tenant — some skip straight to autofill)
- Whether "Create Account" is required before applying, or if some
  tenants allow a guest flow
- Field labels in "My Information" — some tenants add/remove fields
- How "Application Questions" render (radio buttons vs. dropdowns vs.
  free text) — the current matching logic tries text-match first,
  then falls back to a text input

Recommend: run it against 2-3 real Workday links with
`headless=False` (change in `bot.py`'s `pw.chromium.launch(...)`
call) so you can watch what it does and where it gets stuck.

## Next steps

1. Test Workday against real links, fix what breaks.
2. Build Greenhouse handler (native + embedded — same form either
   way).
3. Then iCIMS, Oracle Taleo, Ashby, ADP, and the rest — each added to
   `automation/registry.py` above the generic fallback.
4. Real LinkedIn/Indeed manual-apply-path detection.
5. Real verification-code resume (keep browser context alive between
   the pause and the reply).

## Notes

- Concurrency capped at 3 (`MAX_CONCURRENT_APPLICATIONS` in `bot.py`).
- LinkedIn Easy Apply / Indeed Easy Apply are never auto-submitted —
  only used if a manual-apply alternative exists on the page.
