"""
Arts & Culture Job Search Bot — Bern/Switzerland
Uses SerpApi (Google Jobs) as primary source — real job listings only.
Falls back to direct scraping of museums.ch, kulturboerse.ch, theaterpaedagogik.ch.
"""

import os, json, time, hashlib, requests, re
from datetime import datetime, date
from urllib.parse import quote_plus

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
SERPAPI_KEY        = os.environ.get("SERPAPI_KEY", "")
SEEN_FILE          = "seen_jobs.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
}

# ─── SERPAPI QUERIES ───────────────────────────────────────────────────────────
# (query, tier)  — kept to ≤10 to stay within 100/month free tier
SERPAPI_QUERIES = [
    ("Tontechniker Bern",                   1),
    ("sound engineer theatre Switzerland",  1),
    ("Bühnentechniker Veranstaltung Bern",  1),
    ("Theater Kino Galerie Stelle Bern",    1),
    ("Kulturzentrum Kulturvermittlung Bern",1),
    ("sound design job Switzerland",        1),
    ("BIPOC interkulturell Stelle Schweiz", 2),
    ("Antirassismus Diversität Kultur Bern",2),
    ("Barista Teilzeit Bern Student",       3),
    ("Café Servicemitarbeiter Bern",        3),
]

# ─── RELEVANCE ─────────────────────────────────────────────────────────────────
TIER_KEYWORDS = {
    1: ["ton", "sound", "audio", "technik", "theater", "theatre", "bühne", "kino",
        "galerie", "gallery", "kultur", "culture", "arts", "kunst", "veranstaltung",
        "festival", "musik", "music", "konzert", "cinema", "radio", "kulturvermittlung",
        "kulturzentrum", "kulturhaus", "stage", "event", "vermittlung", "aufsicht"],
    2: ["bipoc", "poc", "black", "schwarz", "diversität", "diversity", "interkulturell",
        "intercultural", "antirassismus", "migrant", "diaspora", "community",
        "postmigrant", "gleichstellung", "empowerment", "inklusiv", "inclusion"],
    3: ["barista", "café", "coffee", "kaffee", "gastro", "service", "restaurant",
        "servicemitarbeiter", "kaffeebar", "hospitality"],
}

JOB_SIGNALS = ["stelle", "job", "stellenangebot", "position", "pensum", "teilzeit",
                "vollzeit", "mitarbeiter", "gesucht", "bewerbung", "wir suchen",
                "hiring", "vacancy", "apply", "praktikum", "assistenz", "%"]

def clean(text: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def sanitise(text: str) -> str:
    """Make text safe for Telegram HTML mode."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def is_relevant(title: str, snippet: str, tier: int) -> bool:
    text = (title + " " + snippet).lower()
    has_kw         = any(kw in text for kw in TIER_KEYWORDS[tier])
    looks_like_job = any(w in text for w in JOB_SIGNALS)
    return has_kw and looks_like_job

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


# ─── SERPAPI FETCHER ───────────────────────────────────────────────────────────

def fetch_serpapi(query: str, tier: int) -> list[dict]:
    params = {
        "engine":  "google_jobs",
        "q":       query,
        "api_key": SERPAPI_KEY,
        "hl":      "de",
        "gl":      "ch",
        "chips":   "date_posted:week",
        "num":     10,
    }
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=20)
        resp.raise_for_status()
    except Exception as e:
        print(f"  SerpApi error for '{query}': {e}")
        return []

    jobs = []
    for item in resp.json().get("jobs_results", []):
        title   = item.get("title", "").strip()
        company = item.get("company_name", "").strip()
        loc     = item.get("location", "").strip()
        snippet = clean(item.get("description", ""))[:200]
        url     = (item.get("share_link")
                   or (item.get("related_links") or [{}])[0].get("link", "")
                   or "https://www.google.com/search?q=" + quote_plus(title))
        if title:
            jobs.append({"title": title, "company": company, "location": loc,
                         "snippet": snippet, "url": url, "source": "Google Jobs"})
    return jobs


# ─── DIRECT SCRAPERS (don't block GitHub Actions) ─────────────────────────────

def scrape_museumsch() -> list[dict]:
    jobs = []
    base = "https://www.museums.ch"
    for page in range(1, 3):
        url = f"{base}/de/fachwelt/angebote/stellenboerse-3036.html" + (f"?page={page}" if page > 1 else "")
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  museums.ch error: {e}"); break

        for m in re.finditer(
            r'href="(/de/fachwelt/angebote/stellenboerse/[^"]+\.html)"[^>]*>(.*?)</a>',
            resp.text, re.DOTALL
        ):
            title = clean(m.group(2))
            lines = [l.strip() for l in title.split('\n') if l.strip() and not l.strip().startswith("Veröff")]
            title = lines[0] if lines else title
            snippet = " ".join(lines[1:3]) if len(lines) > 1 else title
            if len(title) > 4:
                jobs.append({"title": title, "company": "", "location": "Schweiz",
                             "snippet": snippet[:200], "url": base + m.group(1),
                             "source": "museums.ch 🏛️"})
        time.sleep(1)
    return jobs


def scrape_kulturboerse() -> list[dict]:
    jobs = []
    for page in range(3):
        url = f"https://www.kulturboerse.ch/index.php?tmpl=tmplSearch&iType=2&page={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"  kulturboerse.ch error: {e}"); break

        for m in re.finditer(
            r'<strong>([^<]{5,150})</strong>.*?href="([^"]*tmpl=tmplInserat[^"]*)"',
            resp.text, re.DOTALL
        ):
            title = clean(m.group(1))
            href  = m.group(2)
            if not href.startswith("http"):
                href = "https://www.kulturboerse.ch/" + href.lstrip("/")
            if len(title) > 4:
                jobs.append({"title": title, "company": "", "location": "Schweiz",
                             "snippet": title, "url": href, "source": "kulturboerse.ch 🎨"})
        time.sleep(1)
    return jobs


def scrape_theaterpaedagogik() -> list[dict]:
    try:
        resp = requests.get("https://www.theaterpaedagogik.ch/schwarzes-brett/list",
                            headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  theaterpaedagogik.ch error: {e}"); return []

    jobs = []
    for m in re.finditer(
        r'<h[23][^>]*>(.*?)</h[23]>.*?href="(/schwarzes-brett/eintrag/[^"]+)"',
        resp.text, re.DOTALL
    ):
        title = clean(m.group(1))
        if len(title) > 4:
            jobs.append({"title": title, "company": "", "location": "Schweiz",
                         "snippet": title,
                         "url": "https://www.theaterpaedagogik.ch" + m.group(2),
                         "source": "theaterpaedagogik.ch 🎭"})
    # fallback
    if not jobs:
        for m in re.finditer(r'href="(/schwarzes-brett/eintrag/[^"]+)"[^>]*>([^<]{5,150})<', resp.text):
            jobs.append({"title": clean(m.group(2)), "company": "", "location": "Schweiz",
                         "snippet": clean(m.group(2)),
                         "url": "https://www.theaterpaedagogik.ch" + m.group(1),
                         "source": "theaterpaedagogik.ch 🎭"})
    return jobs[:20]


# ─── MAIN FETCH ────────────────────────────────────────────────────────────────

def fetch_all_jobs() -> dict:
    seen    = load_seen()
    new_ids = set()
    results = {1: [], 2: [], 3: []}

    def add(job: dict, tier: int):
        jid = job_id(job["title"], job["url"])
        if jid in seen or jid in new_ids:
            return
        if not is_relevant(job["title"], job["snippet"], tier):
            return
        job["tier"] = tier
        results[tier].append(job)
        new_ids.add(jid)

    # SerpApi — primary source
    if SERPAPI_KEY:
        for query, tier in SERPAPI_QUERIES:
            print(f"[SerpApi T{tier}] {query}")
            for job in fetch_serpapi(query, tier):
                add(job, tier)
            time.sleep(1.2)
    else:
        print("WARNING: No SERPAPI_KEY found — results will be limited")

    # Direct scrapers — supplement with specialist Swiss arts boards
    print("Scraping museums.ch...")
    for job in scrape_museumsch():
        for t in [1, 2, 3]:
            if is_relevant(job["title"], job["snippet"], t):
                add(job, t); break

    print("Scraping kulturboerse.ch...")
    for job in scrape_kulturboerse():
        for t in [1, 2, 3]:
            if is_relevant(job["title"], job["snippet"], t):
                add(job, t); break

    print("Scraping theaterpaedagogik.ch...")
    for job in scrape_theaterpaedagogik():
        for t in [1, 2]:
            if is_relevant(job["title"], job["snippet"], t):
                add(job, t); break

    save_seen(seen | new_ids)
    return results


# ─── TELEGRAM ──────────────────────────────────────────────────────────────────

def send_telegram(text: str):
    """Send one message, guaranteed under 4096 chars."""
    # Truncate safely if somehow still too long
    if len(text) > 4096:
        text = text[:4090] + "…"
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text,
              "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=15
    )
    if not resp.ok:
        print(f"  Telegram error {resp.status_code}: {resp.text}")
        # Retry without HTML parse mode in case of bad markup
        resp2 = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": re.sub(r'<[^>]+>', '', text),
                  "disable_web_page_preview": True},
            timeout=15
        )
        resp2.raise_for_status()


def build_messages(by_tier: dict) -> list[str]:
    today = date.today().strftime("%d %b %Y")
    total = sum(len(v) for v in by_tier.values())

    if not total:
        return [f"🎭 Job digest — {today}\n\nNothing new today — I'll keep looking! 🌱"]

    sections = {
        1: ("🔊 Sound, Theatre & Arts", by_tier[1]),
        2: ("✊ BIPOC & Cultural sector", by_tier[2]),
        3: ("☕ Barista & Hospitality", by_tier[3]),
    }

    messages = []
    current  = f"🎭 <b>Job digest — {today}</b>  ({total} new)\n"
    counter  = 1

    for _, (heading, jobs) in sections.items():
        if not jobs:
            continue
        section = f"\n<b>{heading}</b>\n"
        for job in jobs:
            title   = sanitise(job.get("title", ""))
            company = sanitise(job.get("company", ""))
            loc     = sanitise(job.get("location", ""))
            source  = sanitise(job.get("source", ""))
            url     = job.get("url", "")

            # Validate URL — skip if empty or broken
            if not url or not url.startswith("http"):
                url = "https://www.google.com/search?q=" + quote_plus(job.get("title",""))

            meta = " · ".join(filter(None, [company, loc, source]))
            line = f"{counter}. <a href='{url}'>{title}</a>"
            if meta:
                line += f"\n   <i>{meta}</i>"
            line += "\n"

            # Split into new message if this section would overflow
            if len(current) + len(section) + len(line) > 3800:
                messages.append(current.strip())
                current = section + line
                section = ""
            else:
                section += line
            counter += 1

        current += section

    current += "\nGood luck! 🌟"
    messages.append(current.strip())
    return messages


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    by_tier = fetch_all_jobs()
    print(f"Tier1={len(by_tier[1])}, Tier2={len(by_tier[2])}, Tier3={len(by_tier[3])}")
    messages = build_messages(by_tier)
    print(f"Sending {len(messages)} Telegram message(s)...")
    for i, msg in enumerate(messages, 1):
        print(f"  Message {i}: {len(msg)} chars")
        send_telegram(msg)
        time.sleep(0.8)
    print("Done ✓")

if __name__ == "__main__":
    main()
