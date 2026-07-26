# Job Application Bot — Flow Test (Dummy Logic)

This is stage 1: the Telegram bot interaction flow, running on **dummy
fill logic** so we can validate the UX before wiring up real browser
automation.

## Setup

1. Create a bot with [@BotFather](https://t.me/BotFather) on Telegram
   and grab the token it gives you.

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set your token as an environment variable:
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:your-token-here"
   ```

4. Run the bot:
   ```bash
   python bot.py
   ```

5. Open a chat with your bot on Telegram and send `/start`, then paste
   a batch of links (one per line, or space-separated).

## What's real vs. what's a stub

| Piece | Status |
|---|---|
| Telegram bot: receiving links, streaming per-link status | ✅ Real |
| Verification code request/response flow | ✅ Real (the *conversation* logic — bot correctly pauses, asks, resumes) |
| Actually visiting the job link and filling the form | 🔲 Dummy — `processor.py` picks a random outcome instead |
| Actually submitting a verification code | 🔲 Dummy — `resume_after_verification()` always "succeeds" |

## Next step

Once you're happy with the flow, `processor.py` is where real
automation goes:

- `process_application(link)` → open the link with Playwright, detect
  the ATS platform (Greenhouse / Lever / Workday / etc. — probably
  worth starting with 1-2 platforms), fill the form using your
  pre-supplied Q&A profile, return the real `ApplicationStatus`.
- `resume_after_verification(link, code)` → re-enter the browser
  session (kept alive or re-opened) and submit the code.

Everything else in `bot.py` (link parsing, concurrent processing,
per-link status reporting, the verification pause/resume UX) should
stay as-is.

## Notes / things to keep in mind going forward

- LinkedIn Easy Apply actively detects and can ban accounts for
  automated applications — worth excluding from automation and
  handling manually.
- Concurrency: right now all links process in parallel via
  `asyncio.gather`. Once real browser automation is in, you'll likely
  want to cap concurrency (e.g. 2-3 at a time) to avoid rate limits /
  looking like a bot to the target sites.


