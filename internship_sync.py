"""Civil internship notice synchronizer and source monitor.

Published internship cards are stored separately from student/mock-test data.
Source-page discoveries are kept as review leads unless an individual notice
contains enough reliable details to publish safely.
"""
import hashlib
import re
import ssl
import time
from datetime import date, datetime
from html import unescape
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

import certifi
from bs4 import BeautifulSoup

from app import get_db_connection

USER_AGENT = "CivilCareer-InternshipMonitor/1.0 (+https://civilcareer.onrender.com)"
TIMEOUT = 25
MAX_FETCH_ATTEMPTS = 2
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# Direct listing / official programme pages. Third-party portals are search
# destinations only; their listings are never represented as official notices.
MONITORED_SOURCES = [
    ("AICTE National Internship Portal", "GOVERNMENT_PORTAL", "https://internship.aicte-india.org/internships"),
    ("AICTE CPWD Internship Dashboard", "GOVERNMENT_PORTAL", "https://internship.aicte-india.org/dashboards/cpwd"),
    ("AICTE NHAI Internship Dashboard", "GOVERNMENT_PORTAL", "https://internship.aicte-india.org/dashboards/nhai"),
    ("NHAI Official Internship Portal", "GOVERNMENT", "https://internshipsatnhai.digitalindiacorporation.in/"),
    ("NHAI / MoRTH Official Website", "GOVERNMENT", "https://nhai.gov.in/"),
    ("CPWD Official Website", "GOVERNMENT", "https://cpwd.gov.in/"),
    ("PM Internship Scheme", "GOVERNMENT", "https://pminternship.mca.gov.in/"),
    ("L&T Careers", "EMPLOYER", "https://www.larsentoubro.com/corporate/careers/"),
    ("Tata Projects Careers", "EMPLOYER", "https://www.tataprojects.com/careers/"),
    ("Shapoorji Pallonji Careers", "EMPLOYER", "https://www.shapoorjipallonji.com/careers"),
    ("BHEL Careers", "PSU", "https://careers.bhel.in/"),
    ("NTPC Careers", "PSU", "https://careers.ntpc.co.in/"),
    ("Delhi Metro Careers", "METRO", "https://delhimetrorail.com/careers"),
    ("Hyderabad Metro", "METRO", "https://hmrl.co.in/"),
    ("Internshala Civil Internships", "JOB_PORTAL", "https://internshala.com/internships/civil-engineering-internship/"),
    ("LinkedIn Civil Internships", "JOB_PORTAL", "https://www.linkedin.com/jobs/search/?keywords=civil%20engineering%20intern"),
    ("Indeed India Civil Internships", "JOB_PORTAL", "https://in.indeed.com/jobs?q=civil+engineering+intern"),
    ("Naukri Civil Internships", "JOB_PORTAL", "https://www.naukri.com/civil-engineering-intern-jobs"),
]

# Existing verified notices retained; no student or test data is touched.
SEED_NOTICES = [
    {
        "notice_key": "moefcc-internship-2026",
        "organization": "Ministry of Environment, Forest and Climate Change (MoEF&CC)",
        "title": "MoEF&CC Internship Scheme 2026",
        "discipline": "Multidisciplinary; check the official guidelines for eligible subjects",
        "qualification": "As specified in the official scheme guidelines",
        "location": "As specified by MoEF&CC",
        "duration": "As specified in the official guidelines",
        "stipend": "Check official guidelines",
        "last_date": "2026-12-31",
        "notification_url": "https://portals.moef.gov.in/internship/",
        "apply_url": "https://portals.moef.gov.in/internship/",
        "updates_url": "https://portals.moef.gov.in/internship/",
        "source_name": "MoEF&CC official Internship Portal",
        "source_url": "https://portals.moef.gov.in/internship/",
        "summary": "Applications are open from 1 November to 31 December 2026. Check the scheme guidelines to confirm whether your subject and qualification are eligible.",
    },
    {
        "notice_key": "nhai-winter-term-2026-27",
        "organization": "National Highways Authority of India (NHAI)",
        "title": "Winter Internship 2026–27 and Term Internship 2027",
        "discipline": "Civil Engineering and other listed disciplines",
        "qualification": "Final-year and pre-final-year UG/PG students from eligible recognised institutions; see official notice",
        "location": "125 ongoing National Highway projects and NHAI/IHMCL divisions",
        "duration": "Winter: 1 month (Dec 2026–Jan 2027); Term: 6 months (Jan–Jun 2027)",
        "stipend": "₹20,000 per month (as stated in the PIB announcement)",
        "last_date": "2026-10-20",
        "notification_url": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2299419&lang=1&reg=3",
        "apply_url": "https://internshipsatnhai.digitalindiacorporation.in/",
        "updates_url": "https://internshipsatnhai.digitalindiacorporation.in/",
        "source_name": "PIB / Ministry of Road Transport & Highways",
        "source_url": "https://www.pib.gov.in/PressReleasePage.aspx?PRID=2299419&lang=1&reg=3",
        "summary": "The announced application deadline was 20 October 2026. Applications are closed; institute recommendations were scheduled through 10 November 2026.",
    },
]

CIVIL_TERMS = (
    "civil engineering", "civil intern", "civil internship", "structural",
    "construction", "site engineer", "quantity surveying", "estimation",
    "highway", "bridge", "surveying", "geotechnical", "bim", "autocad",
    "public works", "pwd", "cpwd", "nhai", "metro rail", "building",
)

def fetch_html(url):
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    last_error = None
    for attempt in range(1, MAX_FETCH_ATTEMPTS + 1):
        try:
            with urlopen(req, timeout=TIMEOUT, context=SSL_CONTEXT) as response:
                if "text/html" not in response.headers.get("Content-Type", "text/html").lower():
                    return ""
                return response.read(2_000_000).decode("utf-8", errors="ignore")
        except Exception as exc:
            last_error = exc
            if attempt < MAX_FETCH_ATTEMPTS:
                time.sleep(attempt)
    raise last_error

def clean(value):
    return re.sub(r"\s+", " ", unescape(value or "")).strip()

def is_civil_related(text):
    low = clean(text).lower()
    return any(term in low for term in CIVIL_TERMS)

def monitor_source(db, name, category, url, today):
    """Record source health and discover review leads without inventing facts."""
    try:
        html = fetch_html(url)
        if not html:
            raise ValueError("Source did not return an HTML page")
        soup = BeautifulSoup(html, "html.parser")
        page_title = clean(soup.title.get_text(" ", strip=True)) if soup.title else name
        leads = 0
        seen = set()
        for anchor in soup.find_all("a", href=True):
            title = clean(anchor.get_text(" ", strip=True))
            href = urljoin(url, anchor.get("href", ""))
            if len(title) < 8 or href.startswith(("javascript:", "mailto:", "#")):
                continue
            if urlparse(href).scheme not in ("http", "https"):
                continue
            context = clean(anchor.parent.get_text(" ", strip=True))[:1200]
            if not is_civil_related(title + " " + context):
                continue
            # Avoid turning general category/search pages into notice cards.
            if href.rstrip("/") == url.rstrip("/"):
                continue
            fingerprint = hashlib.sha256((name + "|" + href).encode()).hexdigest()
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            db.execute("""
                INSERT INTO internship_source_leads
                    (lead_key, source_name, source_category, title, url, context,
                     first_seen, last_seen, review_status)
                VALUES (?,?,?,?,?,?,?,?, 'REVIEW')
                ON CONFLICT (lead_key) DO UPDATE SET
                    title=excluded.title, context=excluded.context,
                    last_seen=excluded.last_seen
            """, (fingerprint, name, category, title[:500], href, context, today, today))
            leads += 1
        db.execute("""
            INSERT INTO internship_source_status
                (source_name, source_category, source_url, page_title, status,
                 leads_found, last_checked, last_error)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,'')
            ON CONFLICT (source_name) DO UPDATE SET
                source_category=excluded.source_category,
                source_url=excluded.source_url, page_title=excluded.page_title,
                status=excluded.status, leads_found=excluded.leads_found,
                last_checked=CURRENT_TIMESTAMP, last_error=''
        """, (name, category, url, page_title[:500], "OK", leads))
        return {"source": name, "status": "OK", "leads": leads}
    except Exception as exc:
        db.execute("""
            INSERT INTO internship_source_status
                (source_name, source_category, source_url, page_title, status,
                 leads_found, last_checked, last_error)
            VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP,?)
            ON CONFLICT (source_name) DO UPDATE SET
                source_category=excluded.source_category,
                source_url=excluded.source_url, status=excluded.status,
                last_checked=CURRENT_TIMESTAMP, last_error=excluded.last_error
        """, (name, category, url, "", "ERROR", 0, (type(exc).__name__ + ": " + str(exc))[:1000]))
        return {"source": name, "status": "ERROR", "error": str(exc)[:250]}

def sync_official_internships():
    db = get_db_connection()
    today = date.today().isoformat()
    result = {"sources_checked": 0, "sources_ok": 0, "leads_found": 0,
              "inserted_or_updated": 0, "errors": []}
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS official_internships (
                notice_key TEXT PRIMARY KEY, organization TEXT NOT NULL,
                title TEXT NOT NULL, discipline TEXT, qualification TEXT,
                location TEXT, duration TEXT, stipend TEXT, last_date DATE,
                notification_url TEXT, apply_url TEXT, admit_card_url TEXT,
                result_url TEXT, updates_url TEXT, source_name TEXT, source_url TEXT,
                summary TEXT, status TEXT NOT NULL DEFAULT 'VERIFY',
                last_verified DATE, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS internship_source_status (
                source_name TEXT PRIMARY KEY, source_category TEXT, source_url TEXT,
                page_title TEXT, status TEXT, leads_found INTEGER DEFAULT 0,
                last_checked TIMESTAMP, last_error TEXT
            )
        """)
        db.execute("""
            CREATE TABLE IF NOT EXISTS internship_source_leads (
                lead_key TEXT PRIMARY KEY, source_name TEXT, source_category TEXT,
                title TEXT, url TEXT, context TEXT, first_seen DATE, last_seen DATE,
                review_status TEXT DEFAULT 'REVIEW'
            )
        """)
        for item in SEED_NOTICES:
            status = "OPEN" if item["last_date"] >= today else "CLOSED"
            db.execute("""
                INSERT INTO official_internships
                (notice_key, organization, title, discipline, qualification, location,
                 duration, stipend, last_date, notification_url, apply_url, updates_url,
                 source_name, source_url, summary, status, last_verified, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)
                ON CONFLICT (notice_key) DO UPDATE SET
                  organization=excluded.organization, title=excluded.title,
                  discipline=excluded.discipline, qualification=excluded.qualification,
                  location=excluded.location, duration=excluded.duration,
                  stipend=excluded.stipend, last_date=excluded.last_date,
                  notification_url=excluded.notification_url, apply_url=excluded.apply_url,
                  updates_url=excluded.updates_url, source_name=excluded.source_name,
                  source_url=excluded.source_url, summary=excluded.summary,
                  status=excluded.status, last_verified=excluded.last_verified,
                  updated_at=CURRENT_TIMESTAMP
            """, (
                item["notice_key"], item["organization"], item["title"],
                item["discipline"], item["qualification"], item["location"],
                item["duration"], item["stipend"], item["last_date"],
                item["notification_url"], item["apply_url"], item["updates_url"],
                item["source_name"], item["source_url"], item["summary"], status, today
            ))
            result["inserted_or_updated"] += 1

        for name, category, url in MONITORED_SOURCES:
            result["sources_checked"] += 1
            source_result = monitor_source(db, name, category, url, today)
            if source_result["status"] == "OK":
                result["sources_ok"] += 1
                result["leads_found"] += source_result.get("leads", 0)
            else:
                result["errors"].append(name + ": " + source_result.get("error", "source unavailable"))
            db.commit()
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
