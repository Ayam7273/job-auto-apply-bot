"""
bot.py

Telegram bot flow:
  1. Manage profiles (/newprofile, /setfield, /addqa, /setresume, etc.)
  2. Pick an active profile with /useprofile <name>
  3. Paste job links (one per line, or space-separated) — processed
     against the active profile.
  4. Bot streams a status per link:
       - Success
       - Closed / no longer available
       - Needs email verification code -> bot asks for it, pins the alert
       - Needs assessment -> flagged, not auto-attempted
       - LinkedIn/Indeed Easy-Apply-only -> flagged as Job Not Available
  5. Concurrency is capped so we don't hammer target sites / look bot-like.

Run:
    pip install -r requirements.txt
    Put TELEGRAM_BOT_TOKEN=... in a .env file next to this script
    python bot.py
"""

import asyncio
import logging
import os
import re

from dotenv import load_dotenv
from playwright.async_api import async_playwright
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)

import profiles
from processor import (
    ApplicationStatus,
    STATUS_LABELS,
    process_application,
    resume_after_verification,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(r"https?://\S+")
MAX_CONCURRENT_APPLICATIONS = 3  # cap so we don't hammer target sites

WELCOME_TEXT = (
    "👋 Job application bot.\n\n"
    "First time here? Set up a profile:\n"
    "  /newprofile <name>\n"
    "  /setfield <name> full_name John Doe\n"
    "  /setfield <name> email john@example.com\n"
    "  (send your CV as a file with caption: /setresume <name>)\n"
    "  /addqa <name> | Are you authorized to work in the UK? | Yes\n\n"
    "Then pick it as active for today's batch:\n"
    "  /useprofile <name>\n\n"
    "Then just paste your job links, one per line.\n\n"
    "Type /help to see all commands.\n\n"
    "Automation status: Workday has a real handler. Everything else "
    "(custom career pages, and platforms without a dedicated handler yet) "
    "uses the generic best-effort filler — it only submits when confident, "
    "otherwise it flags for your manual review rather than guessing."
)

HELP_TEXT = (
    "📋 Commands\n\n"
    "Profiles:\n"
    "/newprofile <name> — create a new profile\n"
    "/profiles — list all profiles\n"
    "/useprofile <name> — set active profile for link processing\n"
    "/viewprofile <name> — show a profile's details\n"
    "/deleteprofile <name> — delete a profile\n"
    "/setfield <name> <field> <value> — update full_name, email, phone, "
    "location, linkedin_url, or portfolio_url\n"
    "/setprofile <name> — paste a whole profile at once, one 'Label: Value' "
    "per line (see example below)\n"
    "/addqa <name> | <question> | <answer> — add a Q&A entry\n"
    "/delqa <name> <index> — remove a Q&A entry\n"
    "(send a document with caption /setresume <name> to attach a CV)\n\n"
    "Applying:\n"
    "Just paste links (one per line) once a profile is active.\n"
    "/pending — see applications waiting on a verification code\n\n"
    "Example /setprofile usage:\n"
    "/setprofile ABDUL\n"
    "Full Name: Abdul Njie\n"
    "Phone: 706-395-9218\n"
    "Email: njieabdulakimm@gmail.com\n"
    "Address: 3467 Lehigh Way, Decatur, GA 30034\n"
)


# ---------- helpers ----------

def extract_links(text: str) -> list[str]:
    return URL_PATTERN.findall(text)


def get_active_profile_name(context: ContextTypes.DEFAULT_TYPE) -> str | None:
    return context.user_data.get("active_profile")


def clean_name(raw: str) -> str:
    """Strips accidental angle brackets if someone types a placeholder
    like <name> literally instead of substituting the real value."""
    return raw.strip("<>")


async def reply(update: Update, text: str) -> None:
    await update.message.reply_text(text)


# ---------- profile commands ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, WELCOME_TEXT)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply(update, HELP_TEXT)


async def new_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, "Usage: /newprofile <name>")
        return
    name = clean_name(context.args[0])
    try:
        profiles.create_profile(name)
        await reply(update, f"✅ Created profile '{name}'. Use /setfield to fill it in.")
    except profiles.ProfileError as e:
        await reply(update, f"⚠️ {e}")


async def list_profiles(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    names = profiles.list_profiles()
    if not names:
        await reply(update, "No profiles yet. Create one with /newprofile <name>.")
        return
    active = get_active_profile_name(context)
    lines = ["📁 Profiles:"]
    for n in names:
        marker = " (active)" if n == active else ""
        lines.append(f"  - {n}{marker}")
    await reply(update, "\n".join(lines))


async def use_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, "Usage: /useprofile <name>")
        return
    name = clean_name(context.args[0])
    if not profiles.profile_exists(name):
        await reply(update, f"⚠️ Profile '{name}' doesn't exist. See /profiles.")
        return
    context.user_data["active_profile"] = name
    await reply(update, f"✅ Active profile set to '{name}'. Paste links whenever you're ready.")


async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    name = clean_name(context.args[0]) if context.args else get_active_profile_name(context)
    if not name:
        await reply(update, "Usage: /viewprofile <name>  (or set an active profile first)")
        return
    try:
        await reply(update, profiles.format_profile_summary(name))
    except profiles.ProfileError as e:
        await reply(update, f"⚠️ {e}")


async def delete_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await reply(update, "Usage: /deleteprofile <name>")
        return
    name = clean_name(context.args[0])
    try:
        profiles.delete_profile(name)
        if get_active_profile_name(context) == name:
            context.user_data.pop("active_profile", None)
        await reply(update, f"🗑️ Deleted profile '{name}'.")
    except profiles.ProfileError as e:
        await reply(update, f"⚠️ {e}")


async def set_field(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 3:
        await reply(update, "Usage: /setfield <name> <field> <value...>")
        return
    name, field = clean_name(context.args[0]), context.args[1]
    value = " ".join(context.args[2:])
    try:
        profiles.set_personal_field(name, field, value)
        await reply(update, f"✅ Updated {field} for '{name}'.")
    except profiles.ProfileError as e:
        await reply(update, f"⚠️ {e}")


BULK_FIELD_SYNONYMS = {
    "full_name": ["name", "full name", "legal name"],
    "email": ["email"],
    "phone": ["phone", "phone number", "mobile"],
    "linkedin_url": ["linkedin", "linkedin url"],
    "portfolio_url": ["portfolio", "website", "portfolio url"],
    "password": ["password", "account password"],
    # these all fold into one "location" field, appended in order seen
    "_location_part": ["city, state", "city", "state", "zip code", "zip", "address", "location"],
}


async def bulk_set_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /setprofile <name>  then each following line is "Label  Value"
    (colon or 2+ spaces/tab between label and value). Paste a whole
    profile in one message instead of one /setfield per line.
    """
    if not context.args:
        await reply(update, "Usage: /setprofile <name>  then paste lines like:\nFull Name: Abdul Njie\nPhone: 706-395-9218")
        return
    name = clean_name(context.args[0])
    if not profiles.profile_exists(name):
        await reply(update, f"⚠️ Profile '{name}' doesn't exist. Create it first with /newprofile {name}.")
        return

    # Everything after "/setprofile <name>" on subsequent lines
    body = update.message.text.split("\n", 1)
    if len(body) < 2:
        await reply(update, "Add the profile details on the lines after the command. See /help for the format.")
        return
    lines = [l.strip() for l in body[1].splitlines() if l.strip()]

    updated_fields = []
    location_parts = []
    unmatched = []

    for line in lines:
        # Split on ":" first, else on 2+ spaces/tab
        if ":" in line:
            label, _, value = line.partition(":")
        else:
            parts = re.split(r"\s{2,}|\t", line, maxsplit=1)
            if len(parts) != 2:
                unmatched.append(line)
                continue
            label, value = parts
        label = label.strip().lower()
        value = value.strip()
        if not value:
            continue

        matched_field = None
        for field, synonyms in BULK_FIELD_SYNONYMS.items():
            if label in synonyms:
                matched_field = field
                break

        if matched_field == "_location_part":
            location_parts.append(value)
        elif matched_field:
            profiles.set_personal_field(name, matched_field, value)
            updated_fields.append(matched_field)
        else:
            unmatched.append(line)

    if location_parts:
        profiles.set_personal_field(name, "location", ", ".join(location_parts))
        updated_fields.append("location")

    msg_lines = []
    if updated_fields:
        msg_lines.append(f"✅ Updated for '{name}': {', '.join(sorted(set(updated_fields)))}")
    if unmatched:
        msg_lines.append("⚠️ Couldn't match these lines (use /setfield for them manually):")
        msg_lines.extend(f"  {l}" for l in unmatched)
    await reply(update, "\n".join(msg_lines) if msg_lines else "Nothing recognized in that message.")


async def add_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Usage: /addqa <name> | <question> | <answer>
    raw = update.message.text.partition(" ")[2]  # strip "/addqa"
    parts = [p.strip() for p in raw.split("|")]
    if len(parts) != 3:
        await reply(update, "Usage: /addqa <name> | <question> | <answer>")
        return
    name, question, answer = parts
    try:
        profiles.add_qa(name, question, answer)
        await reply(update, f"✅ Added Q&A to '{name}'.")
    except profiles.ProfileError as e:
        await reply(update, f"⚠️ {e}")


async def del_qa(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) != 2:
        await reply(update, "Usage: /delqa <name> <index>")
        return
    name, idx_str = context.args
    try:
        idx = int(idx_str)
        profiles.remove_qa(name, idx)
        await reply(update, f"🗑️ Removed Q&A [{idx}] from '{name}'.")
    except (ValueError, profiles.ProfileError) as e:
        await reply(update, f"⚠️ {e}")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles a resume/CV upload: send a file with caption '/setresume <name>'."""
    caption = update.message.caption or ""
    match = re.match(r"/setresume\s+(\S+)", caption)
    if not match:
        await reply(
            update,
            "To attach a CV, send the file with caption:  /setresume <profile name>",
        )
        return

    name = match.group(1).strip("<>")
    if not profiles.profile_exists(name):
        await reply(update, f"⚠️ Profile '{name}' doesn't exist. Create it first with /newprofile.")
        return

    doc = update.message.document
    dest_dir = profiles.PROFILES_DIR / name
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / f"resume_{doc.file_name}"

    file = await doc.get_file()
    await file.download_to_drive(custom_path=str(dest_path))
    profiles.set_resume_path(name, str(dest_path))

    await reply(update, f"✅ Resume saved for '{name}'.")


# ---------- link processing ----------

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""

    pending: dict = context.user_data.setdefault("pending_verification", {})
    if pending:
        await try_resolve_verification_reply(update, context, text)
        return

    links = extract_links(text)
    if not links:
        await reply(
            update,
            "I didn't spot any links in that message. Paste job links "
            "(one per line), or type /help for commands.",
        )
        return

    active_name = get_active_profile_name(context)
    if not active_name:
        await reply(
            update,
            "⚠️ No active profile set. Use /profiles to see what you have, "
            "or /newprofile <name> to create one, then /useprofile <name>.",
        )
        return

    profile_data = profiles.load_profile(active_name)

    await reply(update, f"Got {len(links)} link(s). Using profile '{active_name}'. Starting now…")

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_APPLICATIONS)
    numbered_links = list(enumerate(links, start=1))

    async with async_playwright() as pw:
        try:
            browser = await pw.chromium.launch(headless=False)
        except Exception as e:
            logger.exception("Failed to launch browser: %s", e)
            await reply(
                update,
                "⚠️ Couldn't start the browser. Make sure Playwright's browser "
                "binaries are installed — run:  playwright install chromium",
            )
            return

        async def bounded(idx, link):
            async with semaphore:
                await process_and_report(update, context, idx, link, browser, profile_data)

        tasks = [asyncio.create_task(bounded(idx, link)) for idx, link in numbered_links]
        await asyncio.gather(*tasks)
        await browser.close()


async def process_and_report(update, context, idx: int, link: str, browser, profile_data: dict) -> None:
    status = await process_application(browser, link, profile_data)
    label = STATUS_LABELS[status]

    if status == ApplicationStatus.NEEDS_VERIFICATION:
        pending = context.user_data.setdefault("pending_verification", {})
        pending[idx] = link
        msg = await update.message.reply_text(
            f"🚨 [{idx}] {label}\n{link}\n\n"
            f"Reply with:  {idx} <code>   to continue this one."
        )
        try:
            await context.bot.pin_chat_message(
                chat_id=update.effective_chat.id,
                message_id=msg.message_id,
                disable_notification=False,
            )
        except Exception as e:
            logger.warning("Couldn't pin verification message: %s", e)
    else:
        await update.message.reply_text(f"[{idx}] {label}\n{link}")


async def try_resolve_verification_reply(update, context, text: str) -> None:
    pending: dict = context.user_data.get("pending_verification", {})
    match = re.match(r"\s*(\d+)\s+(\S+)\s*$", text)

    if not match:
        await reply(
            update,
            "I've got pending verification(s). Reply in the format: "
            "<link number> <code>  e.g.  \"3 482913\".  Or /pending to see the list.",
        )
        return

    idx = int(match.group(1))
    code = match.group(2)

    link = pending.get(idx)
    if not link:
        await reply(update, f"No pending verification for link [{idx}]. Check the number and try again.")
        return

    await reply(update, f"[{idx}] Submitting code…")
    status = await resume_after_verification(link, code)
    label = STATUS_LABELS[status]
    await update.message.reply_text(f"[{idx}] {label}\n{link}")

    del pending[idx]


async def show_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    pending: dict = context.user_data.get("pending_verification", {})
    if not pending:
        await reply(update, "Nothing pending right now.")
        return
    lines = ["🚨 Pending verification codes:"]
    for idx, link in pending.items():
        lines.append(f"  [{idx}] {link}")
    lines.append("\nReply with:  <number> <code>")
    await reply(update, "\n".join(lines))


# ---------- entrypoint ----------

def main() -> None:
    load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    proxy_url = os.environ.get("TELEGRAM_PROXY_URL")
    if not token:
        raise RuntimeError(
            "Set TELEGRAM_BOT_TOKEN env var (get one from @BotFather on Telegram)."
        )

    builder = (
        ApplicationBuilder()
        .token(token)
        .connect_timeout(30)
        .read_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(30)
    )
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)

    app: Application = builder.build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("newprofile", new_profile))
    app.add_handler(CommandHandler("profiles", list_profiles))
    app.add_handler(CommandHandler("useprofile", use_profile))
    app.add_handler(CommandHandler("viewprofile", view_profile))
    app.add_handler(CommandHandler("deleteprofile", delete_profile))
    app.add_handler(CommandHandler("setfield", set_field))
    app.add_handler(CommandHandler("setprofile", bulk_set_profile))
    app.add_handler(CommandHandler("addqa", add_qa))
    app.add_handler(CommandHandler("delqa", del_qa))
    app.add_handler(CommandHandler("pending", show_pending))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting…")
    app.run_polling()


if __name__ == "__main__":
    main()