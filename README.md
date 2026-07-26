# Job Application Bot

## Stage 2: Profiles + platform-aware dummy processing

What's new in this stage:

* **Multi-profile support** — create, edit, and switch between multiple
applicant profiles (name, email, phone, CV, Q\&A pairs).
* **LinkedIn/Indeed handling** — links to these platforms are flagged
as "Job Not Available" unless a manual-apply option is detected
(currently simulated; real detection needs Playwright — see below).
* **Concurrency cap** — max 3 links processed in parallel at once.
* **Pinned verification alerts** — when a link needs an email
verification code, the bot pins that message in the chat so it's
hard to miss, on top of the normal `\[idx] <code>` reply flow.

Form-filling itself is still **dummy logic** — `processor.py` picks a
random outcome. Real Playwright automation is the next stage, once
we've analyzed your actual batch of ATS links.

## Setup

```bash
pip install -r requirements.txt
```

Put your token in a `.env` file next to `bot.py`:

```
TELEGRAM\_BOT\_TOKEN=123456:your-token-here
```

Run:

```bash
python bot.py
```

## Commands

**Profiles**

```
/newprofile <name>                          create a new profile
/profiles                                    list all profiles
/useprofile <name>                           set active profile for link processing
/viewprofile <name>                          show a profile's details
/deleteprofile <name>                        delete a profile
/setfield <name> <field> <value>             update full\_name, email, phone,
                                              location, linkedin\_url, or portfolio\_url
/addqa <name> | <question> | <answer>        add a Q\&A entry
/delqa <name> <index>                        remove a Q\&A entry
```

To attach a CV: send the file as a document in Telegram with the
caption `/setresume <name>`.

**Applying**

```
paste links (one per line)     processes them against the active profile
/pending                       see links waiting on a verification code
```

## Data layout

```
profiles/
  <name>/
    profile.json      # personal info, resume path, Q\&A pairs
    resume\_<file>      # uploaded CV
```

## Next step: real automation

Once you paste your 200-300 links, next steps are:

1. Bucket links by domain to see your actual ATS distribution
(`platform\_detector.py` already has signatures for Greenhouse,
Lever, Workday, iCIMS, SmartRecruiters — will extend based on
what shows up).
2. Build real Playwright handlers per platform, starting with
whichever 1-2 platforms are most common in your batch.
3. Add a generic fallback handler for unrecognized platforms (best
effort field-matching, flagged for manual review if it can't
confidently fill something).
4. Replace the LinkedIn/Indeed dummy simulation in `processor.py`
with real page inspection: check if a manual-apply option exists
alongside Easy Apply, use it if so, otherwise flag as unavailable.
5. `resume\_after\_verification()` gets wired to actually re-enter the
browser session and submit the code.

## Notes going forward

* LinkedIn Easy Apply / Indeed Easy Apply are never auto-submitted —
only used if a manual-apply alternative exists on the page.
* Concurrency capped at 3 to avoid rate limits / bot-like patterns
against target sites. Adjust `MAX\_CONCURRENT\_APPLICATIONS` in
`bot.py` if needed.

