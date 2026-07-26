"""
profiles.py

Stores applicant profiles as JSON files under profiles/<name>/profile.json,
with each profile's resume/cover letter saved alongside it.

A profile looks like:
{
  "name": "default",
  "personal": {
    "full_name": "",
    "email": "",
    "phone": "",
    "location": "",
    "linkedin_url": "",
    "portfolio_url": ""
  },
  "resume_path": "profiles/default/resume.pdf",
  "cover_letter_path": "profiles/default/cover_letter.pdf",
  "qa": [
    {"question": "Are you authorized to work in the UK?", "answer": "Yes"},
    {"question": "Years of experience with Python", "answer": "2"}
  ]
}

qa is a list (not a dict) because job forms phrase the same question many
different ways — when real form-filling goes in, we'll fuzzy-match the
form's question text against these to find the closest answer.
"""

import json
import os
from pathlib import Path
from typing import Optional

PROFILES_DIR = Path("profiles")

DEFAULT_APPLICATION_PASSWORD = "RemoteJob2024!"

EMPTY_PROFILE_TEMPLATE = {
    "personal": {
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "linkedin_url": "",
        "portfolio_url": "",
        "password": DEFAULT_APPLICATION_PASSWORD,
    },
    "resume_path": None,
    "cover_letter_path": None,
    "qa": [],
}

ALLOWED_PERSONAL_FIELDS = set(EMPTY_PROFILE_TEMPLATE["personal"].keys())


class ProfileError(Exception):
    pass


def _profile_dir(name: str) -> Path:
    return PROFILES_DIR / name


def _profile_json_path(name: str) -> Path:
    return _profile_dir(name) / "profile.json"


def profile_exists(name: str) -> bool:
    return _profile_json_path(name).exists()


def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    return sorted(
        p.name for p in PROFILES_DIR.iterdir()
        if p.is_dir() and (p / "profile.json").exists()
    )


def create_profile(name: str) -> dict:
    if profile_exists(name):
        raise ProfileError(f"Profile '{name}' already exists.")
    _profile_dir(name).mkdir(parents=True, exist_ok=True)
    data = {"name": name, **json.loads(json.dumps(EMPTY_PROFILE_TEMPLATE))}
    _save(name, data)
    return data


def load_profile(name: str) -> dict:
    if not profile_exists(name):
        raise ProfileError(f"Profile '{name}' doesn't exist.")
    with open(_profile_json_path(name), "r", encoding="utf-8") as f:
        return json.load(f)


def _save(name: str, data: dict) -> None:
    with open(_profile_json_path(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def delete_profile(name: str) -> None:
    if not profile_exists(name):
        raise ProfileError(f"Profile '{name}' doesn't exist.")
    import shutil
    shutil.rmtree(_profile_dir(name))


def set_personal_field(name: str, field: str, value: str) -> dict:
    if field not in ALLOWED_PERSONAL_FIELDS:
        raise ProfileError(
            f"Unknown field '{field}'. Valid fields: {', '.join(sorted(ALLOWED_PERSONAL_FIELDS))}"
        )
    data = load_profile(name)
    data["personal"][field] = value
    _save(name, data)
    return data


def set_resume_path(name: str, file_path: str) -> dict:
    data = load_profile(name)
    data["resume_path"] = file_path
    _save(name, data)
    return data


def set_cover_letter_path(name: str, file_path: str) -> dict:
    data = load_profile(name)
    data["cover_letter_path"] = file_path
    _save(name, data)
    return data


def add_qa(name: str, question: str, answer: str) -> dict:
    data = load_profile(name)
    data["qa"].append({"question": question, "answer": answer})
    _save(name, data)
    return data


def remove_qa(name: str, index: int) -> dict:
    data = load_profile(name)
    if index < 0 or index >= len(data["qa"]):
        raise ProfileError(f"No Q&A entry at index {index}.")
    data["qa"].pop(index)
    _save(name, data)
    return data


def format_profile_summary(name: str) -> str:
    data = load_profile(name)
    p = data["personal"]
    lines = [f"👤 Profile: {name}", ""]
    lines.append(f"Name: {p['full_name'] or '(not set)'}")
    lines.append(f"Email: {p['email'] or '(not set)'}")
    lines.append(f"Phone: {p['phone'] or '(not set)'}")
    lines.append(f"Location: {p['location'] or '(not set)'}")
    lines.append(f"LinkedIn: {p['linkedin_url'] or '(not set)'}")
    lines.append(f"Portfolio: {p['portfolio_url'] or '(not set)'}")
    lines.append(f"Account password (used for any site requiring sign-up): {p['password']}")
    lines.append(f"Resume: {'✅ uploaded' if data['resume_path'] else '❌ not uploaded'}")
    lines.append(f"Cover letter: {'✅ uploaded' if data['cover_letter_path'] else '(not set)'}")
    lines.append("")
    lines.append(f"Q&A entries: {len(data['qa'])}")
    for i, qa in enumerate(data["qa"]):
        lines.append(f"  [{i}] Q: {qa['question']}")
        lines.append(f"       A: {qa['answer']}")
    return "\n".join(lines)