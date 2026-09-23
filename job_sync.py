"""Official-source government job synchronizer for Civil Career."""
import hashlib
import re
from datetime import datetime
from html import unescape
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

from app import get_db_connection

USER_AGENT = "CivilCareer-OfficialJobSync/1.0"
TIMEOUT = 25

OFFICIAL_SOURCES = [
    ("UPSC", "https://www.upsc.gov.in/recruitment/recruitment-advertisement", "https://upsconline.nic.in/"),
    ("SSC", "https://ssc.gov.in/", "https://ssc.gov.in/"),
    ("NHAI", "https://nhai.gov.in/nhai/taxonomy/term/248", "https://nhai.gov.in/"),
]

CIVIL_KEYWORDS = (
    "civil", "junior engineer", "assistant engineer", "executive engineer",
    "deputy manager (technical)", "technical", "structural", "highway",
    "roads", "construction", "works", "survey", "geotechnical",
    "water resources", "quantity"
)

def fetch_html(url):
    req = Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    })
    with urlopen(req, timeout=TIMEOUT) as response:
        return response.read().decode("utf-8", errors="ignore")

def clean(value):
    return re.sub(r"\s+", " ", unescape(value or "")).strip()

def civil_relevant(value):
    text = clean(value).lower()
    return any(k in text for k in CIVIL_KEYWORDS)

def discover(source_name, listing_url, apply_url):
    soup = BeautifulSoup(fetch_html(listing_url), "html.parser")
    results = []
    seen = set()

    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        href = urljoin(listing_url, a.get("href", ""))
        if len(title) < 8 or href.startswith(("javascript:", "#", "mailto:")):
            continue

        # UPSC advertisement pages expose generic "Advertisement No.X" titles.
        # Keep those official notices for later verification instead of using
        # third-party job portals.
        if source_name == "UPSC":
            if not re.search(r"advertisement\s+no\.?\s*\d+", title, re.I):
                continue
        elif not civil_relevant(title + " " + clean(a.parent.get_text(" ", strip=True))):
            continue

        key = (source_name, title.lower(), href)
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "organization": source_name,
            "post_name": title[:500],
            "notification_url": href,
            "apply_url": apply_url,
        })

    return results[:40]

def notification_number(item):
    match = re.search(
        r"(?:advertisement|advt\.?|notice|post\s*code)[^0-9]{0,8}([A-Za-z0-9/-]+)",
        item["post_name"], re.I
    )
    if match:
        return match.group(1)[:80]
    return hashlib.sha1(item["notification_url"].encode()).hexdigest()[:16]

def sync_official_jobs():
    summary = {"sources_checked": 0, "new_jobs": 0, "updated_jobs": 0, "errors": []}
    db = get_db_connection()
    today = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        for source, url, apply_url in OFFICIAL_SOURCES:
            summary["sources_checked"] += 1
            try:
                items = discover(source, url, apply_url)
                for item in items:
                    existing = db.execute(
                        "SELECT id FROM government_jobs WHERE organization=? AND post_name=? LIMIT 1",
                        (item["organization"], item["post_name"])
                    ).fetchone()

                    if existing:
                        db.execute(
                            """UPDATE government_jobs
                               SET notification_url=?, apply_url=?, source=?,
                                   last_verified=?, updated_at=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (item["notification_url"], item["apply_url"], source,
                             today, existing["id"])
                        )
                        summary["updated_jobs"] += 1
                        continue

                    is_civil = civil_relevant(item["post_name"])
                    cursor = db.execute(
                        """INSERT OR IGNORE INTO government_jobs
                        (organization, post_name, department, job_type,
                         qualification, branch, vacancies, age_limit,
                         age_relaxation, salary, pay_level,
                         application_start, application_last_date, exam_date,
                         application_fee, selection_process, job_location,
                         notification_url, apply_url, source,
                         notification_number, notification_date, last_verified, status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            item["organization"], item["post_name"],
                            "Government / PSU Recruitment",
                            "Government Recruitment",
                            "See official notification for exact eligibility.",
                            "Civil Engineering" if is_civil else "Engineering",
                            "See official notification", "See official notification",
                            "", "See official notification", "",
                            None, None, None, "See official notification",
                            "See official notification", "India",
                            item["notification_url"], item["apply_url"], source,
                            notification_number(item), today, today, "NEW"
                        )
                    )

                    if cursor.lastrowid:
                        summary["new_jobs"] += 1
                        students = db.execute(
                            "SELECT user_id FROM user_job_preferences WHERE notifications_enabled=1"
                        ).fetchall()
                        for student in students:
                            db.execute(
                                """INSERT OR IGNORE INTO job_notifications
                                   (user_id, job_id, notification_type, message)
                                   VALUES (?,?,?,?)""",
                                (
                                    student["user_id"], cursor.lastrowid,
                                    "NEW_OFFICIAL_JOB",
                                    f"New official government job notification: {item['post_name']}"
                                )
                            )

                db.commit()
            except Exception as exc:
                db.rollback()
                summary["errors"].append(f"{source}: {type(exc).__name__}: {exc}")
    finally:
        db.close()

    return summary
