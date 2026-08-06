"""
job_alert.py
Checks public job APIs/RSS feeds for fresher-friendly roles matching your
criteria, and sends new matches to Telegram. Designed to run hourly via
GitHub Actions (see .github/workflows/job-alert.yml).

Sources used (all public, no login/scraping-ban risk):
  - RemoteOK API        (remote jobs, has tags)
  - Arbeitnow API       (general job board, some remote/India listings)
  - Indeed RSS feeds    (public RSS, no auth required)

NOTE: LinkedIn and Naukri are intentionally NOT scraped here. Both explicitly
prohibit automated scraping in their Terms of Service and are known to ban
accounts tied to it. For those two, keep your existing LinkedIn "Job Alerts"
email/app notifications turned on — they already do this natively and safely.
"""

import json
import os
import re
import sys
from pathlib import Path
from xml.etree import ElementTree

import requests

# ---------------------------------------------------------------------------
# CONFIG — tweak these freely
# ---------------------------------------------------------------------------

ROLE_KEYWORDS = [
    # .NET & C#
    ".net", "dotnet", "asp.net", "c#",
    
    # Python
    "python", "django", "flask", "fastapi",
    
    # Java
    "java", "spring", "spring boot",
    
    # Full Stack, Frontend, Backend
    "full stack", "fullstack", "full-stack",
    "frontend", "front end", "front-end", "react", "angular", "vue",
    "backend", "back end", "back-end",
    
    # Automation Testing & QA
    "automation testing", "qa automation", "sdet", "automation engineer",
    "test automation", "qa engineer", "software tester", "testing",
    
    # General Software Development & Testing
    "software engineer", "software developer", "developer", "engineer",
    "developer trainee", "software engineer trainee", "associate engineer",
]

LOCATION_KEYWORDS = ["hyderabad", "india", "work from home", "wfh"]

FRESHER_KEYWORDS = [
    "fresher", "entry level", "entry-level", "graduate", "trainee",
    "junior", "0-1 year", "0-2 years", "campus", "associate engineer",
    "intern", "internship", "new grad", "new graduate",
    "no experience", "recent graduate", "graduate engineer",
]

# Non-IT / Non-Dev Roles to explicitly exclude/skip
EXCLUDE_KEYWORDS = [
    "bpo", "call center", "telecaller", "customer support", "voice process",
    "non voice", "sales", "marketing", "data entry", "business development",
    "hr recruiter", "content writer", "accountant", "digital marketing"
]

# Indeed RSS search queries — add/remove (query, location) pairs as you like.
INDEED_QUERIES = [
   ('.net OR python OR java OR "full stack" OR "automation testing" OR "software developer"', "Hyderabad"),
    ('.net OR python OR java OR "full stack" OR "automation testing" OR "software developer"', "Remote"),
]

SEEN_FILE = Path(__file__).parent / "seen_jobs.json"
MAX_SEEN_STORED = 800

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

# ---------------------------------------------------------------------------


def load_seen():
    if SEEN_FILE.exists():
        try:
            return set(json.loads(SEEN_FILE.read_text()))
        except (json.JSONDecodeError, ValueError):
            return set()
    return set()


def save_seen(seen_set):
    trimmed = list(seen_set)[-MAX_SEEN_STORED:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=2))


def text_matches(*fields, keywords):
    blob = " ".join(f for f in fields if f).lower()
    return any(kw in blob for kw in keywords)


def job_is_relevant(title, description, location):
    if text_matches(title, description, keywords=EXCLUDE_KEYWORDS):
        return False
    role_ok = text_matches(title, description, keywords=ROLE_KEYWORDS)
    loc_ok = text_matches(title, description, location, keywords=LOCATION_KEYWORDS)
    return role_ok and loc_ok


def job_is_fresher_flagged(title, description):
    return text_matches(title, description, keywords=FRESHER_KEYWORDS)


# ---------------------------------------------------------------------------
# SOURCE: RemoteOK
# ---------------------------------------------------------------------------

def fetch_remoteok():
    jobs = []
    try:
        resp = requests.get(
            "https://remoteok.com/api",
            headers={"User-Agent": "Mozilla/5.0 (job-alert-bot)"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[remoteok] fetch failed: {e}", file=sys.stderr)
        return jobs

    for item in data:
        if not isinstance(item, dict) or "id" not in item:
            continue  # first element is a legal notice, skip it
        title = item.get("position", "")
        company = item.get("company", "")
        location = item.get("location", "Remote")
        description = item.get("description", "") or ""
        url = item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}"

        if job_is_relevant(title, description, location):
            jobs.append({
                "id": f"remoteok:{item.get('id')}",
                "title": title,
                "company": company,
                "location": location or "Remote",
                "url": url,
                "source": "RemoteOK",
                "fresher_flagged": job_is_fresher_flagged(title, description),
            })
    return jobs


# ---------------------------------------------------------------------------
# SOURCE: Arbeitnow
# ---------------------------------------------------------------------------

def fetch_arbeitnow():
    jobs = []
    try:
        resp = requests.get(
            "https://www.arbeitnow.com/api/job-board-api",
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as e:
        print(f"[arbeitnow] fetch failed: {e}", file=sys.stderr)
        return jobs

    for item in data.get("data", []):
        title = item.get("title", "")
        company = item.get("company_name", "")
        location = item.get("location", "")
        description = item.get("description", "") or ""
        url = item.get("url", "")
        slug = item.get("slug", url)

        if job_is_relevant(title, description, location):
            jobs.append({
                "id": f"arbeitnow:{slug}",
                "title": title,
                "company": company,
                "location": location or ("Remote" if item.get("remote") else ""),
                "url": url,
                "source": "Arbeitnow",
                "fresher_flagged": job_is_fresher_flagged(title, description),
            })
    return jobs


# ---------------------------------------------------------------------------
# SOURCE: Indeed RSS
# ---------------------------------------------------------------------------

def fetch_indeed_rss():
    jobs = []
    for query, location in INDEED_QUERIES:
        url = "https://www.indeed.co.in/rss"
        params = {"q": query, "l": location}
        try:
            resp = requests.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (job-alert-bot)"},
                timeout=15,
            )
            resp.raise_for_status()
            root = ElementTree.fromstring(resp.content)
        except (requests.RequestException, ElementTree.ParseError) as e:
            print(f"[indeed] fetch failed for '{query}' @ '{location}': {e}", file=sys.stderr)
            continue

        for item in root.findall(".//item"):
            title_el = item.find("title")
            link_el = item.find("link")
            desc_el = item.find("description")

            title = title_el.text if title_el is not None else ""
            link = link_el.text if link_el is not None else ""
            description = re.sub(r"<[^>]+>", " ", desc_el.text or "") if desc_el is not None else ""

            # Indeed RSS titles are usually "Job Title - Company - Location"
            parts = [p.strip() for p in title.split(" - ")]
            job_title = parts[0] if parts else title
            company = parts[1] if len(parts) > 1 else "Unknown"
            job_location = parts[2] if len(parts) > 2 else location

            if job_is_relevant(job_title, description, job_location):
                jobs.append({
                    "id": f"indeed:{link}",
                    "title": job_title,
                    "company": company,
                    "location": job_location,
                    "url": link,
                    "source": "Indeed",
                    "fresher_flagged": job_is_fresher_flagged(job_title, description),
                })
    return jobs


# ---------------------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------------------

def send_telegram_digest(jobs):
    if not jobs:
        return
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials missing — skipping send. "
              "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.", file=sys.stderr)
        return

    lines = [f"🔔 *{len(jobs)} new job match(es)*\n"]
    for j in jobs:
        flag = "🟢 fresher-flagged" if j["fresher_flagged"] else ""
        lines.append(
            f"*{escape_md(j['title'])}*\n"
            f"{escape_md(j['company'])} · {escape_md(j['location'])} · {j['source']} {flag}\n"
            f"{j['url']}\n"
        )
    message = "\n".join(lines)

    # Telegram messages cap at 4096 chars — split into chunks if needed
    chunks = [message[i:i+3800] for i in range(0, len(message), 3800)]

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in chunks:
        try:
            resp = requests.post(
                api_url,
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": chunk,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            if resp.status_code != 200:
                print(f"[telegram] send failed: {resp.status_code} {resp.text}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"[telegram] send failed: {e}", file=sys.stderr)


def escape_md(text):
    # Minimal escaping for Telegram legacy Markdown mode
    for ch in ["_", "*", "`", "["]:
        text = text.replace(ch, f"\\{ch}")
    return text


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    seen = load_seen()

    all_jobs = []
    all_jobs.extend(fetch_remoteok())
    all_jobs.extend(fetch_arbeitnow())
    all_jobs.extend(fetch_indeed_rss())

    new_jobs = [j for j in all_jobs if j["id"] not in seen]

    print(f"Fetched {len(all_jobs)} matching jobs total, {len(new_jobs)} new.")

    if new_jobs:
        send_telegram_digest(new_jobs)
        seen.update(j["id"] for j in new_jobs)
        save_seen(seen)
    else:
        print("No new matches this run.")


if __name__ == "__main__":
    main()
