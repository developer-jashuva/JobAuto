# Job Alert Bot

Checks job listings every hour and sends new matches to your Telegram. You
review and apply manually — nothing here auto-applies to anything.

## What it checks

- **RemoteOK** and **Arbeitnow** (public JSON APIs)
- **Indeed** (public RSS feed)

LinkedIn and Naukri are **not** scraped — both ban accounts for automated
access per their Terms of Service. Keep LinkedIn's own "Job Alerts" email
notifications on for those (Jobs tab → create a search → toggle "Get job
alerts") — it's free, official, and covers that gap safely.

## Filter logic (edit in `job_alert.py`)

A job is sent to you if:
- Title/description mentions one of: `.NET, React, Python, AI` (or close variants), **AND**
- Title/location mentions: `Hyderabad` or `Remote`

Jobs additionally get a 🟢 "fresher-flagged" tag if they mention words like
"fresher", "entry level", "graduate", "trainee" — but aren't filtered out if
they don't, since many genuinely fresher-friendly postings don't use those
exact words. Adjust `ROLE_KEYWORDS`, `LOCATION_KEYWORDS`, and
`FRESHER_KEYWORDS` at the top of `job_alert.py` any time.

## Setup (15 minutes)

### 1. Create a Telegram bot
1. Open Telegram, message **@BotFather**
2. Send `/newbot`, follow the prompts, name it whatever you like
3. It'll give you a **bot token** — save it, looks like `123456:ABC-defGhIjk...`
4. Message your new bot anything (e.g. "hi") so it can message you back
5. Visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser
   (replace `<YOUR_TOKEN>`), find `"chat":{"id":123456789...}` in the response
   — that number is your **chat ID**

### 2. Create a GitHub repo
1. Create a new **public** repo (private repos have limited free Actions
   minutes, but 2000/month free minutes is usually enough either way)
2. Upload all files from this folder, preserving the `.github/workflows/`
   folder structure

### 3. Add your secrets
In the repo: **Settings → Secrets and variables → Actions → New repository secret**
- Add `TELEGRAM_BOT_TOKEN` = your bot token
- Add `TELEGRAM_CHAT_ID` = your chat ID

### 4. Test it
Go to the **Actions** tab → **Hourly Job Alert** → **Run workflow** (this
uses the `workflow_dispatch` trigger) to fire it manually and confirm you get
a Telegram message.

Once that works, it'll run automatically every hour on its own — no further
action needed.

## Notes
- GitHub Actions free tier: 2,000 minutes/month for private repos, unlimited
  for public repos. This job takes seconds per run, so you're nowhere near
  any limit.
- The bot **deduplicates** — you'll only be notified about a job once,
  tracked via `seen_jobs.json`, which the workflow commits back to the repo
  after each run.
- If a source's API changes or goes down temporarily, that source is skipped
  for that run (logged as a warning) rather than crashing the whole script.
