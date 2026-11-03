"""Official internship notices for Civil Career.

This table is separate from government_jobs and never modifies student or test data.
"""
from datetime import date
from app import get_db_connection

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

def sync_official_internships():
    db = get_db_connection()
    today = date.today().isoformat()
    result = {"checked": 0, "inserted_or_updated": 0}
    try:
        db.execute("""
            CREATE TABLE IF NOT EXISTS official_internships (
                notice_key TEXT PRIMARY KEY,
                organization TEXT NOT NULL,
                title TEXT NOT NULL,
                discipline TEXT,
                qualification TEXT,
                location TEXT,
                duration TEXT,
                stipend TEXT,
                last_date DATE,
                notification_url TEXT,
                apply_url TEXT,
                admit_card_url TEXT,
                result_url TEXT,
                updates_url TEXT,
                source_name TEXT,
                source_url TEXT,
                summary TEXT,
                status TEXT NOT NULL DEFAULT 'VERIFY',
                last_verified DATE,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        for item in SEED_NOTICES:
            status = "OPEN" if item["last_date"] >= today else "CLOSED"
            db.execute("""
                INSERT INTO official_internships
                (notice_key, organization, title, discipline, qualification,
                 location, duration, stipend, last_date, notification_url,
                 apply_url, updates_url, source_name, source_url, summary,
                 status, last_verified, updated_at)
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
                item["source_name"], item["source_url"], item["summary"],
                status, today
            ))
            result["inserted_or_updated"] += 1
            result["checked"] += 1
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
