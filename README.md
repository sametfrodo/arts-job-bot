# 🎭 Arts & Culture Job Search Bot — Bern/Switzerland

A free Telegram bot personalised for your job search in the arts, sound, BIPOC cultural
sector, and hospitality — focused on Bern, Basel, Biel, and Switzerland.

---

## What it searches for

### 🔊 Tier 1 — Sound, Theatre & Arts (your main focus)
- Sound technician / Tontechniker roles in Bern, Basel, Biel
- Stage tech and event tech (Bühnentechnik, Veranstaltungstechnik)
- Theatre jobs in Bern (part-time / Teilzeit friendly)
- Cinema (Kino), gallery (Galerie), cultural centre (Kulturzentrum) roles
- Sound design internships in Switzerland
- Arts assistant positions

### ✊ Tier 2 — BIPOC & POC Cultural Sector
- BIPOC and POC cultural organisations in Switzerland
- Intercultural / anti-racism / diversity organisations
- Black community organisations in Bern
- Migrant and diaspora cultural work

### ☕ Tier 3 — Barista & Hospitality (backup)
- Part-time barista jobs in Bern
- Student café/coffee shop positions

Swiss 🇨🇭 results always appear first within each section.

---

## Setup (about 15 minutes)

### Step 1 — Create your Telegram bot

1. Open Telegram → search for **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy your **bot token** (looks like `123456789:ABCdef...`)

Then get your Chat ID:
1. Start a conversation with your new bot (press Start)
2. Open this in your browser (replace YOUR_TOKEN):
   `https://api.telegram.org/botYOUR_TOKEN/getUpdates`
3. Find the number after `"id":` inside `"chat":` — that's your Chat ID

### Step 2 — Put the code on GitHub

1. Go to https://github.com → create a free account if needed
2. Click **+** → **New repository** → name it `arts-job-bot` → set to **Private**
3. Upload these files:
   - `job_scraper.py`
   - `requirements.txt`
   - `.github/workflows/daily_job_search.yml`

   For the workflow file: when uploading, type `.github/workflows/daily_job_search.yml`
   as the filename — GitHub will create the folders automatically.

### Step 3 — Add your secrets

Go to your repository → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Your token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID number |
| `SERPAPI_KEY` | *(optional)* From https://serpapi.com — 100 free searches/month |

Without SerpApi the bot uses Google News RSS (free, no key needed, slightly less precise).
With SerpApi you get structured Google Jobs results — recommended.

### Step 4 — Test it

1. Go to the **Actions** tab in your repository
2. Click **Daily Arts Job Search** → **Run workflow** → **Run workflow**
3. After ~60 seconds, check Telegram — your first digest should arrive!

---

## Customising

All the important settings are at the top of `job_scraper.py`:

### Add or remove search queries
```python
QUERIES = [
    ("Tontechnik Stelle Bern", 1),   # tier 1 = main priority
    ("BIPOC Kultur Bern",      2),   # tier 2 = BIPOC sector
    ("Barista Bern Teilzeit",  3),   # tier 3 = backup
    # Add your own here!
]
```

### Adjust keywords
```python
TIER_KEYWORDS = {
    1: ["ton", "sound", "theater", ...],   # add more niche terms
    2: ["bipoc", "diaspora", ...],
    3: ["barista", "café", ...],
}
```

### Change the time it runs
In `.github/workflows/daily_job_search.yml`:
```yaml
- cron: "0 8 * * *"   # 8:00 AM UTC = 9:00 AM Swiss time (winter) / 10:00 AM (summer)
```
Use https://crontab.guru to pick a time. Switzerland is UTC+1 in winter, UTC+2 in summer.

---

## Useful Swiss job sites to check manually too

- **jobs.ch** — https://www.jobs.ch
- **jobup.ch** — https://www.jobup.ch
- **culturejobs.ch** — https://www.culturejobs.ch (arts-specific!)
- **kulturjobs.ch** — https://www.kulturjobs.ch
- **stellenmarkt.ch** — https://www.stellenmarkt.ch
- **indeed.ch** — https://ch.indeed.com

---

## Troubleshooting

**No message arrived**
→ Check the Actions tab — red = error. Click the run to see details.
→ Confirm secrets are named exactly right (case-sensitive).

**"Unauthorized" error**
→ Your bot token is wrong. Re-copy it from BotFather.

**"Chat not found" error**
→ Make sure you sent your bot at least one message first.
→ Your Chat ID might be negative (normal for groups).

**Too many irrelevant results**
→ Add terms to `EXCLUDE_KEYWORDS` in the script.
→ Remove any queries from `QUERIES` that aren't working well.

**SerpApi limit hit**
→ Reduce the number of queries in `QUERIES` (aim for ≤10 to stay within 100/month free tier).
→ Or switch `"date_posted:week"` to `"date_posted:month"` to search less frequently.
