"""
Arts & Culture Job Search Bot — personalised for Bern/Switzerland
Searches for jobs in sound, theatre, arts, BIPOC cultural sector,
cinemas, galleries, and (as backup) hospitality/barista work.
Sends a daily Telegram digest, grouped by priority tier.
"""

import os
import json
import time
import hashlib
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date
from urllib.parse import quote_plus

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
SERPAPI_KEY        = os.environ.get("SERPAPI_KEY", "")

RESULTS_PER_QUERY = 5
SEEN_FILE = "seen_jobs.json"

# ─── SEARCH QUERIES ────────────────────────────────────────────────────────────
# Grouped into tiers. Each entry is (query_string, tier).
# Tier 1 = your main interests, Tier 2 = BIPOC / community work, Tier 3 = backup

QUERIES = [

    # ── Tier 1: Sound & Theatre ──────────────────────────────────────────────
    ("Tontechnik Stelle Bern",                  1),
    ("Tontechniker Bern Basel Biel",            1),
    ("sound technician job Bern Switzerland",   1),
    ("sound engineer Bern theatre",             1),
    ("Bühnentechnik Stelle Bern",               1),   # stage tech
    ("Theater Bern Stelle Teilzeit",            1),   # theatre Bern part-time
    ("Kino Stelle Bern Basel",                  1),   # cinema jobs
    ("Galerie Stelle Bern",                     1),   # gallery jobs
    ("Kulturzentrum Stelle Bern",               1),   # cultural centre
    ("Veranstaltungstechnik Bern",              1),   # event tech
    ("sound design internship Switzerland",     1),
    ("arts assistant job Bern Switzerland",     1),
    ("Musikveranstaltung Technik Stelle Bern",  1),   # music event tech

    # ── Tier 2: BIPOC / POC cultural sector ─────────────────────────────────
    ("BIPOC Kulturorganisation Schweiz Stelle", 2),
    ("POC Kulturprojekt Bern Basel Stelle",     2),
    ("Black community organisation job Bern",   2),
    ("interkulturell Kulturprojekt Stelle Bern",2),   # intercultural
    ("antirassismus Organisation Stelle Schweiz",2),  # anti-racism org
    ("Diversität Kulturprojekt Stelle Bern",    2),   # diversity culture
    ("BIPOC arts initiative job Switzerland",   2),
    ("migrantische Kulturarbeit Stelle Schweiz",2),   # migrant cultural work

    # ── Tier 3: Barista / hospitality backup ────────────────────────────────
    ("Barista Stelle Bern Teilzeit",            3),   # part-time barista Bern
    ("Café Bern Aushilfe Student",              3),   # café student help
    ("Barista job Bern student",                3),
]

# ─── RELEVANCE FILTERS ─────────────────────────────────────────────────────────

# Per-tier inclusion keywords — a result must match at least one
TIER_KEYWORDS = {
    1: [
        "ton", "sound", "audio", "technik", "theater", "theatre", "bühne",
        "kino", "galerie", "gallery", "kultur", "culture", "arts", "kunst",
        "veranstaltung", "festival", "musik", "music", "studio", "konzert",
        "concert", "event", "cinema", "production",
    ],
    2: [
        "bipoc", "poc", "black", "schwarz", "diversität", "diversity",
        "interkulturell", "intercultural", "antirassismus", "anti-racism",
        "rassismus", "migrant", "diaspora", "community", "inklusiv",
        "inclusion", "gleichstellung", "empowerment",
    ],
    3: [
        "barista", "café", "coffee", "kaffee", "gastro", "service",
        "hospitality", "aushilfe", "restaurant",
    ],
}

# Hard exclusions — skip regardless of tier
EXCLUDE_KEYWORDS = [
    "vollzeit nur", "full-time only", "10 jahre erfahrung",
    "senior only", "unpaid",
]

# Swiss locations we care about (used to boost relevance scoring)
SWISS_LOCATIONS = ["bern", "basel", "biel", "bienne", "schweiz", "switzerland", "suisse", "svizzera"]


# ─── HELPERS ───────────────────────────────────────────────────────────────────

def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def job_id(title: str, url: str) -> str:
    return hashlib.md5(f"{title}{url}".encode()).hexdigest()

def is_relevant(title: str, snippet: str, tier: int) -> bool:
    text = (title + " " + snippet).lower()
    has_keyword  = any(kw in text for kw in TIER_KEYWORDS[tier])
    has_exclusion = any(kw in text for kw in EXCLUDE_KEYWORDS)
    return has_keyword and not has_exclusion

def is_swiss_or_local(title: str, snippet: str, location: str) -> bool:
    """Returns True if the listing seems to be in Switzerland / our target region."""
    text = (title + " " + snippet + " " + location).lower()
    return any(loc in text for loc in SWISS_LOCATIONS)


# ─── JOB FETCHING ──────────────────────────────────────────────────────────────

def fetch_via_serpapi(query: str) -> list[dict]:
    params = {
        "engine":   "google_jobs",
        "q":        query,
        "api_key":  SERPAPI_KEY,
        "num":      RESULTS_PER_QUERY,
        "hl":       "de",          # German language results (Swiss default)
        "gl":       "ch",          # Swiss Google
        "chips":    "date_posted:week",
    }
    resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    jobs = []
    for item in data.get("jobs_results", []):
        jobs.append({
            "title":    item.get("title", ""),
            "company":  item.get("company_name", ""),
            "location": item.get("location", ""),
            "snippet":  item.get("description", "")[:250],
            "url":      item.get("share_link") or (item.get("related_links") or [{}])[0].get("link", ""),
            "source":   "Google Jobs",
        })
    return jobs


def fetch_via_google_rss(query: str) -> list[dict]:
    """Fallback — Google News RSS, Swiss edition, no API key needed."""
    encoded = quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=de&gl=CH&ceid=CH:de"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as e:
        print(f"  RSS failed for '{query}': {e}")
        return []
    jobs = []
    try:
        root = ET.fromstring(resp.text)
    except ET.ParseError:
        return []
    for item in root.findall(".//item")[:RESULTS_PER_QUERY]:
        title   = item.findtext("title", "").strip()
        link    = item.findtext("link", "").strip()
        snippet = item.findtext("description", "").strip()[:250]
        if title and link:
            jobs.append({
                "title":    title,
                "company":  "",
                "location": "",
                "snippet":  snippet,
                "url":      link,
                "source":   "Google News",
            })
    return jobs


def fetch_all_jobs() -> dict[int, list[dict]]:
    """
    Run all queries. Returns a dict keyed by tier:
      { 1: [job, ...], 2: [job, ...], 3: [job, ...] }
    """
    seen    = load_seen()
    new_ids = set()
    results: dict[int, list[dict]] = {1: [], 2: [], 3: []}

    for query, tier in QUERIES:
        print(f"[Tier {tier}] Searching: {query}")
        try:
            jobs = fetch_via_serpapi(query) if SERPAPI_KEY else fetch_via_google_rss(query)
        except Exception as e:
            print(f"  Error: {e}")
            jobs = []

        for job in jobs:
            jid = job_id(job["title"], job["url"])
            if jid in seen or jid in new_ids:
                continue
            if not is_relevant(job["title"], job["snippet"], tier):
                continue
            # For tiers 1 & 2, lightly prefer Swiss results but don't exclude
            job["swiss"] = is_swiss_or_local(job["title"], job["snippet"], job["location"])
            job["tier"]  = tier
            results[tier].append(job)
            new_ids.add(jid)

        time.sleep(1.2)

    # Sort each tier: Swiss results first
    for t in results:
        results[t].sort(key=lambda j: (not j["swiss"]))

    save_seen(seen | new_ids)
    return results


# ─── TELEGRAM ──────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()


def format_job(i: int, job: dict) -> str:
    title   = job["title"].replace("&", "&amp;").replace("<", "&lt;")
    company = job["company"].replace("&", "&amp;") if job["company"] else ""
    loc     = job["location"] if job["location"] else ""
    flag    = " 🇨🇭" if job.get("swiss") else ""
    meta    = " · ".join(filter(None, [company, loc]))
    line    = f"{i}. <a href='{job['url']}'>{title}</a>{flag}"
    if meta:
        line += f"\n   <i>{meta}</i>"
    return line


def format_digest(by_tier: dict[int, list[dict]]) -> list[str]:
    """
    Returns a list of message strings (Telegram has a 4096-char limit,
    so we split into multiple messages if needed).
    """
    today  = date.today().strftime("%d %b %Y")
    total  = sum(len(v) for v in by_tier.values())
    blocks = []

    header = (
        f"🎭 <b>Your daily job digest — {today}</b>\n"
        f"Found <b>{total}</b> new listings\n"
    )

    sections = {
        1: ("🔊 Sound, Theatre &amp; Arts", by_tier[1]),
        2: ("✊ BIPOC &amp; Cultural sector", by_tier[2]),
        3: ("☕ Barista &amp; Hospitality (backup)", by_tier[3]),
    }

    current = header
    counter = 1

    for tier, (heading, jobs) in sections.items():
        if not jobs:
            continue
        section = f"\n<b>{heading}</b>\n"
        for job in jobs:
            section += format_job(counter, job) + "\n"
            counter += 1
        # Telegram limit: 4096 chars — split if needed
        if len(current) + len(section) > 3800:
            blocks.append(current.strip())
            current = section
        else:
            current += section

    if not total:
        current = (
            f"🎭 <b>Your daily job digest — {today}</b>\n\n"
            "Nothing new today — I'll keep looking! 🌱"
        )

    current += "\nGood luck! 🌟"
    blocks.append(current.strip())
    return blocks


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting job search — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    by_tier = fetch_all_jobs()
    total   = sum(len(v) for v in by_tier.values())
    print(f"Found: Tier1={len(by_tier[1])}, Tier2={len(by_tier[2])}, Tier3={len(by_tier[3])}")

    messages = format_digest(by_tier)
    for msg in messages:
        send_telegram(msg)
        time.sleep(0.5)
    print(f"Sent {len(messages)} Telegram message(s) ✓")


if __name__ == "__main__":
    main()
