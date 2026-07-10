"""
Arts & Culture Job Search Bot — Bern/Switzerland
Scrapes real Swiss job boards directly for actual job listings.
Sends a daily Telegram digest grouped by priority tier.

Sources:
  - kulturboerse.ch  (Swiss cultural jobs board — Migros Kulturprozent)
  - museums.ch       (Swiss museum jobs board)
  - theaterpaedagogik.ch (theatre/pedagogy noticeboard)
  - culturejobs.ch   (Swiss arts jobs)
  - kulturjobs.ch    (German-language Swiss arts jobs)
  - jobs.ch          (general Swiss job board)
  - jobup.ch         (general Swiss job board)
"""

import os, json, time, hashlib, requests, re
from datetime import datetime, date
from urllib.parse import quote_plus

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
SEEN_FILE = "seen_jobs.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ─── RELEVANCE KEYWORDS per tier ──────────────────────────────────────────────
TIER_KEYWORDS = {
    1: [
        "ton", "sound", "audio", "technik", "theater", "theatre", "bühne",
        "kino", "galerie", "gallery", "kultur", "culture", "arts", "kunst",
        "veranstaltung", "festival", "musik", "music", "studio", "konzert",
        "cinema", "production", "medien", "radio", "kulturvermittlung",
        "kulturzentrum", "kulturhaus", "bühnen", "stage", "event",
        "vermittlung", "aufsicht", "empfang", "besucherservice",
    ],
    2: [
        "bipoc", "poc", "black", "schwarz", "diversität", "diversity",
        "interkulturell", "intercultural", "antirassismus", "rassismus",
        "migrant", "diaspora", "community", "postmigrant", "gleichstellung",
        "empowerment", "inclusion", "inklusiv",
    ],
    3: [
        "barista", "café", "coffee", "kaffee", "gastro", "service",
        "hospitality", "restaurant", "servicemitarbeiter", "kaffeebar",
    ],
}

JOB_SIGNALS = [
    "stelle", "job", "stellenangebot", "position", "pensum", "teilzeit",
    "vollzeit", "mitarbeiter", "gesucht", "bewerbung", "wir suchen",
    "hiring", "vacancy", "apply", "praktikum", "praktikant", "volontariat",
    "hospitanz", "assistenz", "%",
]

EXCLUDE = ["news", "artikel", "bericht", "pressemitteilung", "review"]

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

def clean(text: str) -> str:
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).strip()

def is_relevant(title: str, snippet: str, tier: int) -> bool:
    text = (title + " " + snippet).lower()
    has_kw        = any(kw in text for kw in TIER_KEYWORDS[tier])
    has_exc       = any(ex in text for ex in EXCLUDE)
    looks_like_job = any(w in text for w in JOB_SIGNALS)
    return has_kw and looks_like_job and not has_exc

def get(url: str, **kwargs) -> requests.Response:
    return requests.get(url, headers=HEADERS, timeout=15, **kwargs)


# ─── SCRAPER: kulturboerse.ch ─────────────────────────────────────────────────
# Migros Kulturprozent's Swiss cultural jobs board — multiple pages

def scrape_kulturboerse() -> list[dict]:
    """
    kulturboerse.ch lists jobs at:
    https://www.kulturboerse.ch/index.php?tmpl=tmplSearch&iType=2&page=N
    Each listing expands inline; titles and links are in <li> elements.
    We scrape pages 0-3 (4 pages of ~20 listings each).
    """
    jobs = []
    for page in range(4):
        url = f"https://www.kulturboerse.ch/index.php?tmpl=tmplSearch&iType=2&page={page}"
        try:
            resp = get(url)
            resp.raise_for_status()
        except Exception as e:
            print(f"  kulturboerse p{page} error: {e}")
            break

        # Listings appear as <strong>Title</strong> inside <li> tags
        # with a detail link pattern like: tmpl=tmplInserat&iId=XXXXX
        # Extract title + link pairs
        pattern = re.compile(
            r'<li[^>]*>.*?<strong>(.*?)</strong>.*?'
            r'href="([^"]*tmpl=tmplInserat[^"]*)"',
            re.DOTALL
        )
        for m in pattern.finditer(resp.text):
            title = clean(m.group(1))
            href  = m.group(2)
            if not href.startswith("http"):
                href = "https://www.kulturboerse.ch/" + href.lstrip("/")
            if len(title) > 4:
                jobs.append({
                    "title": title, "company": "", "location": "Schweiz",
                    "snippet": title,  # title IS the snippet for relevance check
                    "url": href, "source": "kulturboerse.ch 🎨",
                })

        # Also grab snippet text from expanded listing blocks
        # (the full text is already inline on the page)
        block_pattern = re.compile(
            r'<strong>([^<]{5,150})</strong>(.*?)</li>',
            re.DOTALL
        )
        for m in block_pattern.finditer(resp.text):
            title   = clean(m.group(1))
            snippet = clean(m.group(2))[:200]
            # Skip if we already captured via main pattern
            if any(j["title"] == title for j in jobs):
                continue
            if len(title) > 4 and any(w in snippet.lower() for w in JOB_SIGNALS):
                jobs.append({
                    "title": title, "company": "", "location": "Schweiz",
                    "snippet": snippet,
                    "url": "https://www.kulturboerse.ch/index.php?tmpl=tmplSearch&iType=2",
                    "source": "kulturboerse.ch 🎨",
                })

        time.sleep(1)

    return jobs


# ─── SCRAPER: museums.ch ──────────────────────────────────────────────────────
# Swiss museum association job board — clean link structure

def scrape_museumsch() -> list[dict]:
    """
    museums.ch Stellenbörse — listings are <a> links with full titles inline.
    URL pattern: /de/fachwelt/angebote/stellenboerse/SLUG.html
    Scrapes pages 1-3.
    """
    jobs = []
    base = "https://www.museums.ch"
    for page in range(1, 4):
        if page == 1:
            url = f"{base}/de/fachwelt/angebote/stellenboerse-3036.html"
        else:
            url = f"{base}/de/fachwelt/angebote/stellenboerse-3036.html?page={page}"
        try:
            resp = get(url)
            resp.raise_for_status()
        except Exception as e:
            print(f"  museums.ch p{page} error: {e}")
            break

        pattern = re.compile(
            r'<a href="(/de/fachwelt/angebote/stellenboerse/[^"]+\.html)"[^>]*>(.*?)</a>',
            re.DOTALL
        )
        for m in pattern.finditer(resp.text):
            href    = m.group(1)
            content = clean(m.group(2))
            # The link text contains "Veröffentlicht am: DATE Title Org Snippet"
            # Split on newlines to get title
            lines = [l.strip() for l in content.split('\n') if l.strip()]
            if not lines:
                continue
            # First line is often "Veröffentlicht am: DD.MM.YYYY"
            title_lines = [l for l in lines if not l.startswith("Veröffentlicht")]
            title   = title_lines[0] if title_lines else lines[0]
            snippet = " ".join(title_lines[1:3]) if len(title_lines) > 1 else title
            if len(title) > 4:
                jobs.append({
                    "title": title, "company": "", "location": "Schweiz",
                    "snippet": snippet[:200],
                    "url": base + href,
                    "source": "museums.ch 🏛️",
                })

        time.sleep(1)

    return jobs


# ─── SCRAPER: theaterpaedagogik.ch ────────────────────────────────────────────
# Swiss theatre pedagogy noticeboard

def scrape_theaterpaedagogik() -> list[dict]:
    """
    theaterpaedagogik.ch Schwarzes Brett — listings rendered server-side.
    Each entry has a title heading and a link like:
    /schwarzes-brett/eintrag/SLUG
    """
    url = "https://www.theaterpaedagogik.ch/schwarzes-brett/list"
    try:
        resp = get(url)
        resp.raise_for_status()
    except Exception as e:
        print(f"  theaterpaedagogik.ch error: {e}")
        return []

    jobs = []
    # Entries: <a href="/schwarzes-brett/eintrag/SLUG">
    # Title is in the <h3> or <h2> just before each link
    pattern = re.compile(
        r'<h[23][^>]*>\s*(.*?)\s*</h[23]>.*?'
        r'<a href="(/schwarzes-brett/eintrag/[^"]+)"',
        re.DOTALL
    )
    for m in pattern.finditer(resp.text):
        title = clean(m.group(1))
        href  = m.group(2)
        if len(title) > 4:
            jobs.append({
                "title": title, "company": "", "location": "Schweiz",
                "snippet": title,
                "url": "https://www.theaterpaedagogik.ch" + href,
                "source": "theaterpaedagogik.ch 🎭",
            })

    # Fallback: grab all entry links with surrounding text
    if not jobs:
        for m in re.finditer(r'href="(/schwarzes-brett/eintrag/[^"]+)"[^>]*>([^<]{5,150})<', resp.text):
            title = clean(m.group(2))
            if len(title) > 4:
                jobs.append({
                    "title": title, "company": "", "location": "Schweiz",
                    "snippet": title,
                    "url": "https://www.theaterpaedagogik.ch" + m.group(1),
                    "source": "theaterpaedagogik.ch 🎭",
                })

    return jobs[:20]


# ─── SCRAPER: culturejobs.ch ──────────────────────────────────────────────────

def scrape_culturejobs(term: str) -> list[dict]:
    url = f"https://www.culturejobs.ch/jobs?search={quote_plus(term)}"
    try:
        resp = get(url)
        resp.raise_for_status()
    except Exception as e:
        print(f"  culturejobs.ch error: {e}"); return []

    jobs = []
    for m in re.finditer(r'href="(https://www\.culturejobs\.ch/jobs/[^"]+)"[^>]*>(.*?)</a>', resp.text, re.DOTALL):
        title = clean(m.group(2))
        if 5 < len(title) < 150:
            jobs.append({"title": title, "company": "", "location": "Schweiz",
                         "snippet": title, "url": m.group(1), "source": "culturejobs.ch ✨"})
    return jobs[:8]


# ─── SCRAPER: kulturjobs.ch ───────────────────────────────────────────────────

def scrape_kulturjobs(term: str) -> list[dict]:
    url = f"https://www.kulturjobs.ch/?s={quote_plus(term)}"
    try:
        resp = get(url)
        resp.raise_for_status()
    except Exception as e:
        print(f"  kulturjobs.ch error: {e}"); return []

    jobs = []
    for m in re.finditer(r'<h2[^>]*class="[^"]*entry-title[^"]*"[^>]*>.*?<a href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.DOTALL):
        title = clean(m.group(2))
        if 5 < len(title) < 150:
            jobs.append({"title": title, "company": "", "location": "Schweiz",
                         "snippet": title, "url": m.group(1), "source": "kulturjobs.ch ✨"})
    return jobs[:8]


# ─── SCRAPER: jobs.ch ─────────────────────────────────────────────────────────

def scrape_jobsch(term: str, location: str) -> list[dict]:
    url = (f"https://www.jobs.ch/de/stellenangebote/"
           f"?term={quote_plus(term)}&location={quote_plus(location)}&radius=30")
    try:
        resp = get(url); resp.raise_for_status()
    except Exception as e:
        print(f"  jobs.ch error: {e}"); return []

    jobs = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', resp.text, re.DOTALL):
        try:
            data = json.loads(block)
            for item in (data if isinstance(data, list) else [data]):
                if item.get("@type") not in ("JobPosting", "jobPosting"): continue
                loc_raw = item.get("jobLocation") or {}
                if isinstance(loc_raw, list): loc_raw = loc_raw[0] if loc_raw else {}
                title = item.get("title", "")
                if title:
                    jobs.append({
                        "title": title,
                        "company": (item.get("hiringOrganization") or {}).get("name", ""),
                        "location": (loc_raw.get("address") or {}).get("addressLocality", location),
                        "snippet": clean(item.get("description", ""))[:200],
                        "url": item.get("url", url),
                        "source": "jobs.ch",
                    })
        except Exception: continue
    return jobs[:6]


# ─── SCRAPER: jobup.ch ────────────────────────────────────────────────────────

def scrape_jobupch(term: str, location: str) -> list[dict]:
    url = f"https://www.jobup.ch/de/jobs/?term={quote_plus(term)}&location={quote_plus(location)}"
    try:
        resp = get(url); resp.raise_for_status()
    except Exception as e:
        print(f"  jobup.ch error: {e}"); return []

    jobs = []
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', resp.text, re.DOTALL):
        try:
            data = json.loads(block)
            for item in (data if isinstance(data, list) else [data]):
                if item.get("@type") not in ("JobPosting", "jobPosting"): continue
                loc_raw = (item.get("jobLocation") or {}).get("address") or {}
                title = item.get("title", "")
                if title:
                    jobs.append({
                        "title": title,
                        "company": (item.get("hiringOrganization") or {}).get("name", ""),
                        "location": loc_raw.get("addressLocality", location),
                        "snippet": clean(item.get("description", ""))[:200],
                        "url": item.get("url", url),
                        "source": "jobup.ch",
                    })
        except Exception: continue
    return jobs[:6]


# ─── MAIN FETCH ────────────────────────────────────────────────────────────────

# Targeted searches for jobs.ch / jobup.ch / culturejobs / kulturjobs
TARGETED_SEARCHES = [
    # (term, location, tier)
    ("Tontechniker",          "Bern",        1),
    ("sound technician",      "Bern",        1),
    ("sound engineer",        "Switzerland", 1),
    ("Bühnentechniker",       "Bern",        1),
    ("Veranstaltungstechnik", "Bern",        1),
    ("Theater",               "Bern",        1),
    ("Kino",                  "Bern",        1),
    ("Galerie",               "Bern",        1),
    ("Kulturzentrum",         "Bern",        1),
    ("sound design",          "Switzerland", 1),
    ("BIPOC",                 "Schweiz",     2),
    ("interkulturell",        "Bern",        2),
    ("Antirassismus",         "Schweiz",     2),
    ("Barista",               "Bern",        3),
    ("Café",                  "Bern",        3),
]

CULTUREJOBS_TERMS = ["sound", "theater", "Bühne", "Galerie", "Kino", "BIPOC", "interkulturell"]


def fetch_all_jobs() -> dict:
    seen    = load_seen()
    new_ids = set()
    results = {1: [], 2: [], 3: []}

    def add_job(job: dict, tier: int):
        jid = job_id(job["title"], job["url"])
        if jid in seen or jid in new_ids:
            return
        if not is_relevant(job["title"], job["snippet"], tier):
            return
        job["tier"] = tier
        results[tier].append(job)
        new_ids.add(jid)

    # ── 1. Specialist Swiss arts boards (scrape full listing pages) ───────────

    print("Scraping kulturboerse.ch...")
    for job in scrape_kulturboerse():
        # kulturboerse has Bühne/Technik/Musik categories — check all three tiers
        added = False
        for t in [1, 2, 3]:
            if is_relevant(job["title"], job["snippet"], t):
                add_job(job, t)
                added = True
                break
    time.sleep(1.5)

    print("Scraping museums.ch...")
    for job in scrape_museumsch():
        for t in [1, 2, 3]:
            if is_relevant(job["title"], job["snippet"], t):
                add_job(job, t)
                break
    time.sleep(1.5)

    print("Scraping theaterpaedagogik.ch...")
    for job in scrape_theaterpaedagogik():
        for t in [1, 2]:
            if is_relevant(job["title"], job["snippet"], t):
                add_job(job, t)
                break
    time.sleep(1.5)

    # ── 2. culturejobs.ch / kulturjobs.ch (search-based) ─────────────────────
    for term in CULTUREJOBS_TERMS:
        print(f"culturejobs: {term}")
        for job in scrape_culturejobs(term):
            tier = 2 if any(k in job["title"].lower() for k in ["bipoc", "interkulturell", "diversity"]) else 1
            add_job(job, tier)
        print(f"kulturjobs:  {term}")
        for job in scrape_kulturjobs(term):
            add_job(job, 1)
        time.sleep(1.2)

    # ── 3. General Swiss boards (jobs.ch / jobup.ch) ──────────────────────────
    for term, location, tier in TARGETED_SEARCHES:
        print(f"[Tier {tier}] jobs.ch/jobup: {term} @ {location}")
        for job in scrape_jobsch(term, location):
            add_job(job, tier)
        for job in scrape_jobupch(term, location):
            add_job(job, tier)
        time.sleep(1.2)

    save_seen(seen | new_ids)
    return results


# ─── TELEGRAM ──────────────────────────────────────────────────────────────────

def send_telegram(message: str):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message,
              "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=15
    ).raise_for_status()


def format_digest(by_tier: dict) -> list[str]:
    today = date.today().strftime("%d %b %Y")
    total = sum(len(v) for v in by_tier.values())

    if not total:
        return [f"🎭 <b>Job digest — {today}</b>\n\nNothing new today — I'll keep looking! 🌱"]

    sections = {
        1: ("🔊 Sound, Theatre &amp; Arts", by_tier[1]),
        2: ("✊ BIPOC &amp; Cultural sector", by_tier[2]),
        3: ("☕ Barista &amp; Hospitality", by_tier[3]),
    }

    blocks, counter = [], 1
    current = f"🎭 <b>Job digest — {today}</b>  (<b>{total}</b> new)\n"

    for _, (heading, jobs) in sections.items():
        if not jobs: continue
        section = f"\n<b>{heading}</b>\n"
        for job in jobs:
            title   = job["title"].replace("&","&amp;").replace("<","&lt;")
            meta    = " · ".join(filter(None, [job.get("company",""), job.get("location",""), job.get("source","")]))
            line    = f"{counter}. <a href='{job['url']}'>{title}</a>"
            if meta: line += f"\n   <i>{meta}</i>"
            section += line + "\n"
            counter += 1
        if len(current) + len(section) > 3800:
            blocks.append(current.strip()); current = section
        else:
            current += section

    current += "\nGood luck! 🌟"
    blocks.append(current.strip())
    return blocks


# ─── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Starting — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    by_tier = fetch_all_jobs()
    print(f"Tier1={len(by_tier[1])}, Tier2={len(by_tier[2])}, Tier3={len(by_tier[3])}")
    for msg in format_digest(by_tier):
        send_telegram(msg)
        time.sleep(0.5)
    print("Done ✓")

if __name__ == "__main__":
    main()
