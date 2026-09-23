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
    ("UPSC Recruitment", "https://www.upsc.gov.in/recruitment/criteria-adopted", "https://upsconline.nic.in/"),
]

CIVIL_KEYWORDS = (
    "civil", "junior engineer", "assistant engineer", "executive engineer",
    "deputy manager (technical)", "technical", "structural", "highway",
    "roads", "construction", "works", "survey", "geotechnical",
    "water resources", "quantity", "engineering (structural)", "engineering (soil mechanics)"
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
        elif source_name == "UPSC Recruitment":
            if not civil_relevant(title):
                continue
        elif not civil_relevant(title + " " + clean(a.parent.get_text(" ", strip=True))):
            continue

        key = (source_name, title.lower(), href)
        if key in seen:
            continue
        seen.add(key)
        results.append(enrich_item({
            "organization": source_name,
            "post_name": title[:500],
            "notification_url": href,
            "apply_url": apply_url,
        }))

    return results[:40]


def enrich_item(item):
    title = item["post_name"]
    low = title.lower()
    item.update({
        "department": "Government / PSU Recruitment",
        "job_type": "Central Government",
        "qualification": "See official notification for exact eligibility.",
        "branch": "Civil Engineering",
        "vacancies": "See official notification",
        "age_limit": "See official notification",
        "salary": "See official notification",
        "pay_level": "",
        "application_start": None,
        "application_last_date": None,
        "selection_process": "See official notification",
        "job_location": "India",
        "notification_date": None,
        "status": "NEW",
    })
    match = re.search(r"(?:fill(?:ing)? up|for)\s+(\d+)\s+posts?", low, re.I)
    if match:
        item["vacancies"] = match.group(1)

    if item["organization"] == "NHAI" and "60 posts" in low and "deputy manager (technical)" in low:
        item.update({
            "department": "National Highways Authority of India, Ministry of Road Transport and Highways",
            "job_type": "PSU",
            "qualification": "B.E./B.Tech in Civil Engineering; GATE 2026 Civil Engineering score as specified in the official notice",
            "branch": "Civil Engineering",
            "vacancies": "60",
            "age_limit": "30 years (relaxation as per official rules)",
            "salary": "Rs. 56,100–1,77,500 + applicable allowances",
            "pay_level": "Level 10, 7th CPC",
            "application_start": "2026-05-15",
            "application_last_date": "2026-06-15",
            "selection_process": "Direct recruitment through GATE 2026 score, subject to the official notification",
            "status": "CLOSED",
        })

    if item["organization"] == "SSC" and "junior engineer" in low and "2025" in low:
        item.update({
            "department": "Staff Selection Commission",
            "job_type": "Central Government",
            "branch": "Civil Engineering",
            "selection_process": "SSC Junior Engineer Examination 2025; check official SSC notices for current stage",
            "status": "CLOSED",
        })

    if item["organization"] == "UPSC Recruitment":
        if "assistant professor, civil engineering (structural)" in low:
            item.update({
                "department": "College of Military Engineering, Pune, Ministry of Defence",
                "branch": "Civil Engineering – Structural",
                "vacancies": "1",
                "notification_number": "04/2026 | Vacancy No. 26050403309",
                "notification_date": "2026-09-10",
            })
        elif "assistant professor, civil engineering (soil mechanics)" in low:
            item.update({
                "department": "Ministry of Defence",
                "branch": "Civil Engineering – Soil Mechanics",
                "vacancies": "1",
                "notification_number": "05/2025",
                "notification_date": "2026-06-19",
            })
    return item

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
                               SET department=?, job_type=?, qualification=?, branch=?,
                                   vacancies=?, age_limit=?, salary=?, pay_level=?,
                                   application_start=?, application_last_date=?,
                                   selection_process=?, job_location=?,
                                   notification_url=?, apply_url=?, source=?,
                                   notification_date=?, last_verified=?, status=?,
                                   updated_at=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (
                                item["department"], item["job_type"], item["qualification"],
                                item["branch"], item["vacancies"], item["age_limit"],
                                item["salary"], item["pay_level"], item["application_start"],
                                item["application_last_date"], item["selection_process"],
                                item["job_location"], item["notification_url"], item["apply_url"],
                                source, item["notification_date"] or today, today,
                                item["status"], existing["id"]
                            )
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
                            item["department"],
                            item["job_type"],
                            item["qualification"],
                            item["branch"] if item.get("branch") else ("Civil Engineering" if is_civil else "Engineering"),
                            item["vacancies"], item["age_limit"],
                            "", item["salary"], item["pay_level"],
                            item["application_start"], item["application_last_date"], None,
                            "See official notification", item["selection_process"], item["job_location"],
                            item["notification_url"], item["apply_url"], source,
                            item.get("notification_number") or notification_number(item),
                            item.get("notification_date") or today, today, item["status"]
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
