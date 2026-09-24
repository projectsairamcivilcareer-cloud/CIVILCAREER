from flask import Flask, render_template, request, redirect, url_for, session, send_file
import json
import time
import sqlite3
import re

import psycopg
from psycopg import errors as psycopg_errors
from psycopg.rows import dict_row
import uuid
import random
import os
import secrets
import smtplib
import urllib.request
import urllib.error
from email.message import EmailMessage
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from io import BytesIO
from html import escape
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from gate_mock_engine import GATE_SYLLABI, GATE_SYLLABUS, build_gate_mock, next_difficulty_mode

app = Flask(__name__)

WEBSITE_URL = os.environ.get(
    "WEBSITE_URL",
    "https://civilcareer.up.railway.app"
)

DATA_DIR = os.environ.get(
    "CIVILCAREER_DATA_DIR"
) or (
    "/app/data"
    if os.path.isdir("/app/data")
    else app.root_path
)

os.makedirs(DATA_DIR, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["PROFILE_UPLOAD_FOLDER"] = os.path.join(
    DATA_DIR,
    "profile_uploads"
)
os.makedirs(
    app.config["PROFILE_UPLOAD_FOLDER"],
    exist_ok=True
)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "civil-career-development-key"
)

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# =========================================================
# GLOBAL AUTHENTICATED NAVIGATION
# Keep the application pages full-width and provide one
# compact menu button in the top-left instead of a permanent
# sidebar on every page.
# =========================================================

@app.after_request
def add_global_navigation(response):
    if (
        "student_id" not in session
        or response.status_code != 200
        or not response.content_type
        or not response.content_type.startswith("text/html")
    ):
        return response

    html = response.get_data(as_text=True)

    if "global-menu.css" in html or 'id="cc-global-menu"' in html:
        return response

    asset_version = "20260901"
    assets = (
        f'<link rel="stylesheet" href="/static/css/global-menu.css?v={asset_version}">'
        f'<script defer src="/static/js/global-menu.js?v={asset_version}"></script>'
    )
    html = html.replace("</head>", assets + "</head>", 1)

    response.set_data(html)
    return response



if os.environ.get("RAILWAY_PUBLIC_DOMAIN"):
    app.config["SESSION_COOKIE_SECURE"] = True


# ==============================
# DATABASE CONNECTION
# ==============================

class PostgreSQLCompatConnection:
    """Small SQLite-compatible adapter so existing Civil Career SQL can use PostgreSQL."""

    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _translate_sql(sql, params=None):
        params = tuple(params or ())

        # SQLite uses '?' placeholders; psycopg uses '%s'.
        sql = sql.replace("?", "%s")

        # PostgreSQL equivalent for SQLite's INSERT OR IGNORE.
        if re.match(r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b", sql, re.I):
            sql = re.sub(
                r"^\s*INSERT\s+OR\s+IGNORE\s+INTO\b",
                "INSERT INTO",
                sql,
                count=1,
                flags=re.I,
            )
            sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"

        # SQLite PRAGMA used by the old schema migration code.
        pragma_match = re.match(
            r"^\s*PRAGMA\s+table_info\(([^)]+)\)\s*$",
            sql,
            re.I,
        )
        if pragma_match:
            table_name = pragma_match.group(1).strip().strip("'").strip('"')
            sql = (
                "SELECT column_name AS name "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s "
                "ORDER BY ordinal_position"
            )
            params = (table_name,)

        return sql, params

    def execute(self, sql, params=None):
        sql, params = self._translate_sql(sql, params)
        return self._connection.execute(sql, params)

    def executemany(self, sql, params_seq):
        sql, _ = self._translate_sql(sql, ())
        cursor = self._connection.cursor()
        cursor.executemany(sql, params_seq)
        return cursor

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()


def get_db_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Add Railway PostgreSQL and "
            "reference Postgres.DATABASE_URL from the CIVILCAREER service."
        )

    connection = psycopg.connect(
        database_url,
        row_factory=dict_row,
        connect_timeout=10,
    )
    return PostgreSQLCompatConnection(connection)


# ==============================
# CREATE DATABASE
# ==============================

def migrate_legacy_sqlite(connection, legacy_db):
    """Import existing SQLite data into PostgreSQL without replacing newer data."""
    if not os.path.exists(legacy_db):
        return {"tables": 0, "rows": 0}

    legacy = None
    migrated_tables = 0
    migrated_rows = 0

    try:
        legacy = sqlite3.connect(legacy_db)
        legacy.row_factory = sqlite3.Row

        legacy_tables = legacy.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()

        target_tables = {
            row["table_name"]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            ).fetchall()
        }

        for table_row in legacy_tables:
            table_name = table_row["name"]
            if table_name not in target_tables:
                continue

            legacy_columns = [
                row["name"]
                for row in legacy.execute(
                    f"PRAGMA table_info({table_name})"
                ).fetchall()
            ]
            target_columns = [
                row["column_name"]
                for row in connection.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = %s "
                    "ORDER BY ordinal_position",
                    (table_name,),
                ).fetchall()
            ]

            columns = [name for name in legacy_columns if name in target_columns]
            if not columns:
                continue

            quoted_columns = ", ".join(
                '"' + name.replace('"', '""') + '"'
                for name in columns
            )
            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = (
                f'INSERT INTO "{table_name}" ({quoted_columns}) '
                f"VALUES ({placeholders}) ON CONFLICT DO NOTHING"
            )

            rows = legacy.execute(
                f'SELECT {quoted_columns} FROM "{table_name}"'
            ).fetchall()

            for row in rows:
                connection._connection.execute(
                    insert_sql,
                    tuple(row[name] for name in columns),
                )
                migrated_rows += 1

            if rows:
                migrated_tables += 1

            if "id" in columns and "id" in target_columns:
                try:
                    connection._connection.execute(
                        """
                        SELECT setval(
                            pg_get_serial_sequence(%s, 'id'),
                            COALESCE((SELECT MAX(id) FROM public.%s), 1),
                            true
                        )
                        """.replace("public.%s", f'public."{table_name}"'),
                        (table_name,),
                    )
                except Exception:
                    # Some tables may not have a serial-backed id column.
                    pass

        connection.commit()
        return {"tables": migrated_tables, "rows": migrated_rows}

    except Exception as exc:
        connection.rollback()
        print(
            f"[DB MIGRATION ERROR] {type(exc).__name__}: {exc}",
            flush=True,
        )
        return {"tables": migrated_tables, "rows": migrated_rows}
    finally:
        if legacy is not None:
            legacy.close()


def create_database():

    persistent_db = os.path.join(
        DATA_DIR,
        "civilcareer.db"
    )
    legacy_db = os.path.join(
        app.root_path,
        "civilcareer.db"
    )

    legacy_uploads = os.path.join(
        app.root_path,
        "static",
        "images",
        "profile_uploads"
    )

    if (
        legacy_uploads != app.config["PROFILE_UPLOAD_FOLDER"]
        and os.path.isdir(legacy_uploads)
    ):
        import shutil
        for filename in os.listdir(legacy_uploads):
            source = os.path.join(
                legacy_uploads,
                filename
            )
            target = os.path.join(
                app.config["PROFILE_UPLOAD_FOLDER"],
                filename
            )
            if (
                os.path.isfile(source)
                and not os.path.exists(target)
            ):
                shutil.copy2(
                    source,
                    target
                )

    connection = get_db_connection()


    # ==========================================
    # STUDENTS TABLE
    # ==========================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            education TEXT NOT NULL,
            password TEXT NOT NULL
        )
    """)

    student_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(students)")
    }
    if "profile_photo" not in student_columns:
        connection.execute("ALTER TABLE students ADD COLUMN profile_photo TEXT")
    for column_name, column_type in [
        ("user_id", "TEXT UNIQUE"),
        ("mobile_country_code", "TEXT"),
        ("mobile_number", "TEXT"),
        ("email_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("mobile_verified", "INTEGER NOT NULL DEFAULT 0"),
        ("email_verification_code", "TEXT"),
        ("mobile_verification_code", "TEXT"),
        ("verification_expires_at", "TEXT"),
        ("password_reset_code", "TEXT"),
        ("password_reset_expires_at", "TEXT"),
    ]:
        if column_name not in student_columns:
            connection.execute(f"ALTER TABLE students ADD COLUMN {column_name} {column_type}")


    # ==========================================
    # MOCK TEST HISTORY TABLE
    # ==========================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS mock_test_results (

            id BIGSERIAL PRIMARY KEY,

            student_id INTEGER NOT NULL,

            exam_slug TEXT NOT NULL,

            exam_name TEXT NOT NULL,

            total_questions INTEGER NOT NULL,

            correct INTEGER NOT NULL,

            wrong INTEGER NOT NULL,

            unanswered INTEGER NOT NULL,

            score INTEGER NOT NULL,

            percentage REAL NOT NULL,

            attempt_id TEXT UNIQUE NOT NULL,

            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP

        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS mock_test_feedback (
            id BIGSERIAL PRIMARY KEY,
            student_id INTEGER NOT NULL,
            exam_slug TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comments TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS student_preferences (
            student_id INTEGER PRIMARY KEY,
            target_exam TEXT NOT NULL DEFAULT 'GATE Civil Engineering',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS government_jobs (
            id BIGSERIAL PRIMARY KEY,
            organization TEXT NOT NULL,
            post_name TEXT NOT NULL,
            department TEXT NOT NULL DEFAULT '',
            job_type TEXT NOT NULL DEFAULT '',
            qualification TEXT NOT NULL DEFAULT '',
            branch TEXT NOT NULL DEFAULT '',
            vacancies TEXT NOT NULL DEFAULT '',
            age_limit TEXT NOT NULL DEFAULT '',
            age_relaxation TEXT NOT NULL DEFAULT '',
            salary TEXT NOT NULL DEFAULT '',
            pay_level TEXT NOT NULL DEFAULT '',
            application_start TEXT,
            application_last_date TEXT,
            application_last_datetime TEXT NOT NULL DEFAULT '',
            exam_date TEXT,
            application_fee TEXT NOT NULL DEFAULT '',
            job_role_responsibilities TEXT NOT NULL DEFAULT '',
            selection_process TEXT NOT NULL DEFAULT '',
            job_location TEXT NOT NULL DEFAULT '',
            notification_url TEXT NOT NULL,
            apply_url TEXT NOT NULL,
            source TEXT NOT NULL,
            notification_number TEXT NOT NULL DEFAULT '',
            notification_date TEXT,
            last_verified TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'NEW',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(organization, post_name, notification_number, notification_date)
        )
    """)

    government_job_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(government_jobs)")
    }
    for column_name, column_type in [
        ("application_last_datetime", "TEXT NOT NULL DEFAULT ''"),
        ("job_role_responsibilities", "TEXT NOT NULL DEFAULT ''"),
    ]:
        if column_name not in government_job_columns:
            connection.execute(
                f"ALTER TABLE government_jobs ADD COLUMN {column_name} {column_type}"
            )

    connection.execute("""
        CREATE TABLE IF NOT EXISTS user_job_preferences (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER UNIQUE NOT NULL,
            qualification TEXT NOT NULL DEFAULT '',
            branch TEXT NOT NULL DEFAULT '',
            preferred_states TEXT NOT NULL DEFAULT '',
            job_types TEXT NOT NULL DEFAULT '',
            organizations TEXT NOT NULL DEFAULT '',
            experience TEXT NOT NULL DEFAULT '',
            notifications_enabled INTEGER NOT NULL DEFAULT 1,
            email_enabled INTEGER NOT NULL DEFAULT 0
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS job_notifications (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, job_id, notification_type)
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS notification_alerts (
            id BIGSERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            link_url TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'Civil Career',
            priority TEXT NOT NULL DEFAULT 'NORMAL',
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, category, title, link_url)
        )
    """)
 
    connection.execute("""
        CREATE TABLE IF NOT EXISTS notification_categories (
            id BIGSERIAL PRIMARY KEY,
            category_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            icon TEXT NOT NULL,
            description TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0
        )
    """)
    connection.executemany(
        """
        INSERT INTO notification_categories
        (category_key, name, icon, description, sort_order)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (category_key) DO NOTHING
        """,
        [
            ("EXAMS", "Exam Notifications", "📚", "Exam announcements, applications and important exam updates.", 1),
            ("JOBS", "Job Notifications", "🏛️", "Official Civil Engineering government and PSU recruitment alerts.", 2),
            ("ADMIT_CARDS", "Admit Cards", "🎫", "Admit card and hall-ticket announcements.", 3),
            ("RESULTS", "Results", "🏆", "Exam and recruitment result announcements.", 4),
            ("DEADLINES", "Important Dates", "📅", "Application deadlines, exam dates and other important dates.", 5),
        ]
    )


    seed_jobs = [
        (
            "Union Public Service Commission",
            "Engineering Services (Preliminary) Examination, 2027",
            "Engineering Services",
            "Central Government Examination",
            "Engineering degree in the relevant discipline; Civil Engineering candidates may apply for the Civil Engineering category.",
            "Civil Engineering",
            "As notified by UPSC",
            "As per UPSC ESE 2027 rules",
            "",
            "",
            "As per UPSC notification",
            "2026-09-16",
            "2026-10-06",
            "2026-10-06 23:59",
            "2027-01-31",
            "As per UPSC notification",
            "Engineering Services Examination duties include technical evaluation, engineering design/assessment, field and departmental responsibilities as assigned after selection.",
            "Preliminary examination followed by subsequent stages under ESE rules",
            "All India",
            "https://www.upsc.gov.in/examinations/Engineering%20Services%20%28Preliminary%29%20Examination%2C%202027",
            "https://upsconline.nic.in/",
            "UPSC",
            "ESE-2027",
            "2026-09-16",
            "2026-09-23",
            "OPEN"
        ),
        (
            "National Highways Authority of India",
            "Deputy Manager (Technical)",
            "Technical / Highways",
            "Direct Recruitment",
            "Bachelor's Degree in Civil Engineering from a recognized University or Institute; valid GATE 2026 Civil Engineering score.",
            "Civil Engineering",
            "60",
            "Not exceeding 30 years, subject to applicable relaxation",
            "",
            "",
            "Level 10: Rs. 56,100-1,77,500",
            "2026-05-15",
            "2026-06-15",
            "2026-06-15 23:59",
            "",
            "As per NHAI notification",
            "Technical highway engineering, project supervision, quality control, contract and site-related responsibilities as assigned by NHAI.",
            "Direct recruitment through GATE 2026 score",
            "All India",
            "https://nhai.gov.in/nhai/sites/default/files/vacancy_files/Detailed-Advertisment-DM-Tech-GATE-2026.pdf",
            "https://nhai.gov.in/#/vacancies/current",
            "NHAI",
            "DM-TECH-GATE-2026",
            "2026-05-15",
            "2026-09-23",
            "CLOSED"
        ),
        (
            "Staff Selection Commission",
            "Junior Engineer (Civil, Mechanical & Electrical) Examination, 2026",
            "Junior Engineer",
            "Central Government Examination",
            "Degree or Diploma in the relevant engineering discipline as prescribed by SSC.",
            "Civil Engineering",
            "As notified by SSC",
            "As prescribed by SSC",
            "",
            "",
            "Level 6: Rs. 35,400-1,12,400",
            "2026-03-01",
            "2026-04-01",
            "2026-04-01 23:59",
            "",
            "As per SSC notification",
            "Junior Engineer duties include engineering inspection, measurement, estimation, supervision and technical work as assigned by the department.",
            "Computer Based Examination and subsequent stages as notified by SSC",
            "All India",
            "https://ssc.gov.in/api/attachment/uploads/masterData/ExamCalendar/Tentative_Calendar2026_27_08012026.pdf",
            "https://ssc.gov.in/",
            "SSC",
            "JE-2026",
            "2026-01-08",
            "2026-09-23",
            "CLOSED"
        ),
        (
            "Union Public Service Commission",
            "Assistant Professor, Civil Engineering (Structural)",
            "College of Military Engineering",
            "Direct Recruitment",
            "B.E./B.Tech in Civil Engineering and M.E./M.Tech in Structural Engineering, Structural Design, Dynamics or allied structural fields with First Class or equivalent at either stage.",
            "Civil Engineering",
            "1",
            "35 years for EWS, subject to applicable rules",
            "",
            "",
            "Academic Level 10",
            "2026-05-09",
            "2026-05-29",
            "2026-05-29 23:59",
            "",
            "As per UPSC notification",
            "Teaching, academic, laboratory, curriculum and structural engineering responsibilities associated with the Assistant Professor role.",
            "Shortlisting / Recruitment Test if applicable / Interview",
            "Pune, Maharashtra",
            "https://upsc.gov.in/sites/default/files/AdvtNo-04-2026-Engl-080526.pdf",
            "https://upsconline.nic.in/ora/",
            "UPSC",
            "26050403309",
            "2026-05-08",
            "2026-09-23",
            "CLOSED"
        )
    ]

    connection.executemany(
        """
        INSERT OR IGNORE INTO government_jobs
        (
            organization, post_name, department, job_type,
            qualification, branch, vacancies, age_limit,
            age_relaxation, salary, pay_level,
            application_start, application_last_date, application_last_datetime, exam_date,
            application_fee, job_role_responsibilities, selection_process, job_location,
            notification_url, apply_url, source,
            notification_number, notification_date, last_verified, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        seed_jobs
    )

    # Normalize migrated NHAI GATE 2025 records so outdated/partial legacy rows
    # cannot appear as active jobs with missing mandatory fields.
    connection.execute(
        """
        UPDATE government_jobs
        SET vacancies='40',
            qualification='Bachelor\'s Degree in Civil Engineering from a recognized University or Institute.',
            branch='Civil Engineering',
            age_limit='Not exceeding 30 years, subject to applicable relaxation',
            salary='',
            pay_level='Level 10: Rs. 56,100-1,77,500',
            application_start='2025-05-10',
            application_last_date='2025-07-31',
            application_last_datetime='2025-07-31 18:00',
            application_fee='As per NHAI notification',
            job_role_responsibilities='Technical highway engineering, project supervision, quality control, contract administration, site inspection and related engineering responsibilities assigned by NHAI.',
            selection_process='Direct recruitment through valid GATE 2025 Civil Engineering score, as prescribed by NHAI.',
            job_location='All India',
            notification_url='https://nhai.gov.in/nhai/sites/default/files/vacancy_files/DM-Technical-Detailed-Advt.pdf',
            apply_url='https://nhai.gov.in/',
            source='NHAI',
            notification_number='NHAI-DM-TECH-GATE-2025',
            notification_date='2025-05-10',
            last_verified='2026-09-24',
            status='CLOSED'
        WHERE LOWER(organization) LIKE '%%national highways authority of india%%'
          AND LOWER(post_name) LIKE '%%deputy manager%%technical%%'
          AND (
              LOWER(COALESCE(notification_number,'')) LIKE '%%0592666c5fb30cd8%%'
              OR LOWER(COALESCE(notification_url,'')) LIKE '%%57286%%'
              OR LOWER(COALESCE(post_name,'')) LIKE '%%gate 2025%%'
              OR LOWER(COALESCE(department,'')) LIKE '%%gate 2025%%'
          )
    """
    )

    # Backfill mandatory fields for the built-in official job records.
    connection.execute(
        """
        UPDATE government_jobs
        SET application_last_datetime='2026-10-06 23:59',
            job_role_responsibilities='Engineering Services Examination duties include technical evaluation, engineering design/assessment, field and departmental responsibilities as assigned after selection.'
        WHERE notification_number='ESE-2027'
          AND (application_last_datetime='' OR job_role_responsibilities='')
        """
    )
    connection.execute(
        """
        UPDATE government_jobs
        SET application_last_datetime='2026-06-15 23:59',
            job_role_responsibilities='Technical highway engineering, project supervision, quality control, contract and site-related responsibilities as assigned by NHAI.'
        WHERE notification_number='DM-TECH-GATE-2026'
          AND (application_last_datetime='' OR job_role_responsibilities='')
        """
    )
    connection.execute(
        """
        UPDATE government_jobs
        SET application_last_datetime='2026-04-01 23:59',
            job_role_responsibilities='Junior Engineer duties include engineering inspection, measurement, estimation, supervision and technical work as assigned by the department.'
        WHERE notification_number='JE-2026'
          AND (application_last_datetime='' OR job_role_responsibilities='')
        """
    )
    connection.execute(
        """
        UPDATE government_jobs
        SET application_last_datetime='2026-05-29 23:59',
            job_role_responsibilities='Teaching, academic, laboratory, curriculum and structural engineering responsibilities associated with the Assistant Professor role.'
        WHERE notification_number='26050403309'
          AND (application_last_datetime='' OR job_role_responsibilities='')
        """
    )

    migration_result = migrate_legacy_sqlite(
        connection,
        legacy_db
    )
    print(
        f"[DB MIGRATION] imported {migration_result['rows']} rows "
        f"across {migration_result['tables']} tables",
        flush=True,
    )

    # Generate initial in-app alerts for existing official job data.
    users = connection.execute(
        "SELECT user_id FROM user_job_preferences WHERE notifications_enabled=1"
    ).fetchall()
    jobs = connection.execute(
        """
        SELECT id, organization, post_name, application_last_date,
               exam_date, notification_url, status
        FROM government_jobs
        WHERE notification_url != ''
        ORDER BY notification_date DESC, id DESC
        LIMIT 30
        """
    ).fetchall()
    for user in users:
        for job in jobs:
            priority = "HIGH" if str(job["status"]).upper() == "OPEN" else "NORMAL"
            message = f"{job['organization']}: {job['post_name']}"
            if job["application_last_date"]:
                message += f" | Last date: {job['application_last_date']}"

            categories = ["JOBS"]
            if "examination" in str(job["post_name"]).lower() or "exam" in str(job["post_name"]).lower():
                categories.append("EXAMS")
            if job["application_last_date"]:
                categories.append("DEADLINES")

            for category in categories:
                title_prefix = {
                    "JOBS": "Government Job Update",
                    "EXAMS": "Exam Notification",
                    "DEADLINES": "Important Date",
                }.get(category, "Civil Career Alert")
                connection.execute(
                    """
                    INSERT INTO notification_alerts
                    (user_id, category, title, message, link_url, source, priority)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (user_id, category, title, link_url) DO NOTHING
                    """,
                    (
                        user["user_id"], category,
                        f"{title_prefix}: {job['post_name']}",
                        message,
                        f"/government-jobs/{job['id']}",
                        job["organization"],
                        priority
                    )
                )

    connection.commit()

    connection.close()


# ==============================
# HOME PAGE
# ==============================

@app.route("/")
def home():

    return render_template("index.html")


# ==============================
# ABOUT PAGE
# ==============================

@app.route("/about")
def about():

    return render_template("about.html")


# ==============================
# LOGIN
# ==============================


def _verification_expiry():
    return (datetime.utcnow() + timedelta(minutes=10)).isoformat()


def _send_verification_email(email, code, subject="Civil Career - Email Verification Code", purpose="email verification"):
    body_text = (
        f"Your Civil Career {purpose} code is {code}. "
        "It expires in 10 minutes."
    )

    # Railway-friendly HTTPS delivery. If Resend is configured, use ONLY
    # Resend so a failed API call does not hang for ~20-60 seconds on SMTP.
    resend_api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    resend_from = (
        os.environ.get("RESEND_FROM")
        or os.environ.get("SMTP_FROM")
        or ""
    ).strip()

    if resend_api_key or resend_from:
        if not resend_api_key or not resend_from:
            print(
                "[EMAIL OTP ERROR] Resend configuration incomplete: "
                "RESEND_API_KEY and RESEND_FROM are both required.",
                flush=True,
            )
            return False

        try:
            payload = json.dumps({
                "from": resend_from,
                "to": [email],
                "subject": subject,
                "text": body_text,
            }).encode("utf-8")

            resend_request = urllib.request.Request(
                "https://api.resend.com/emails",
                data=payload,
                headers={
                    "Authorization": f"Bearer {resend_api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "Civil-Career/1.0",
                },
                method="POST",
            )

            with urllib.request.urlopen(resend_request, timeout=15) as response:
                response_body = response.read().decode("utf-8", errors="replace")
                if 200 <= response.status < 300:
                    print(
                        f"[EMAIL OTP] Sent successfully to {email} via Resend",
                        flush=True,
                    )
                    return True

                print(
                    f"[EMAIL OTP ERROR] Resend HTTP {response.status}: "
                    f"{response_body[:500]}",
                    flush=True,
                )
                return False

        except urllib.error.HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                error_body = ""
            print(
                f"[EMAIL OTP ERROR] Resend HTTP {exc.code}: "
                f"{error_body[:500]}",
                flush=True,
            )
            return False
        except Exception as exc:
            print(
                f"[EMAIL OTP ERROR] Resend {type(exc).__name__}: {exc}",
                flush=True,
            )
            return False

    # SMTP fallback is used only when Resend is not configured.
    host = (os.environ.get("SMTP_HOST") or "").strip()
    username = (os.environ.get("SMTP_USERNAME") or "").strip()
    password = os.environ.get("SMTP_PASSWORD") or ""
    sender = (os.environ.get("SMTP_FROM") or username).strip()

    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except (TypeError, ValueError):
        port = 587

    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not username:
        missing.append("SMTP_USERNAME")
    if not password:
        missing.append("SMTP_PASSWORD")
    if not sender:
        missing.append("SMTP_FROM")

    if missing:
        print(
            "[EMAIL OTP ERROR] No usable email delivery configured. "
            "Configure RESEND_API_KEY + RESEND_FROM on Railway.",
            flush=True,
        )
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email
    message.set_content(body_text)

    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as smtp:
                smtp.login(username, password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
                smtp.login(username, password)
                smtp.send_message(message)

        print(f"[EMAIL OTP] Sent successfully to {email} via SMTP", flush=True)
        return True

    except Exception as exc:
        print(
            f"[EMAIL OTP ERROR] SMTP {type(exc).__name__}: {exc}",
            flush=True,
        )
        return False

def _send_verification_sms(country_code, mobile, code):
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    from_number = os.environ.get("TWILIO_FROM_NUMBER")
    if not all([sid, token, from_number]):
        return False
    try:
        from twilio.rest import Client
    except ImportError:
        return False
    Client(sid, token).messages.create(
        body=f"Civil Career verification code: {code}. Expires in 10 minutes.",
        from_=from_number,
        to=f"{country_code}{mobile}",
    )
    return True


def _verification_required(student):
    return not (int(student.get("email_verified") or 0) == 1 and int(student.get("mobile_verified") or 0) == 1)


def _generate_user_id(connection, name):
    base = re.sub(r"[^A-Za-z]", "", str(name or "")).upper()[:3] or "USR"
    while len(base) < 3:
        base += "X"
    for _ in range(100):
        candidate = base + "".join(str(secrets.randbelow(10)) for _ in range(5))
        exists = connection.execute("SELECT id FROM students WHERE user_id=? LIMIT 1", (candidate,)).fetchone()
        if not exists:
            return candidate
    return base + str(random.randint(10000, 99999))


def _profile_incomplete(student, target_exam=None):
    if not student:
        return True
    required = [
        str(student["name"] or "").strip(),
        str(student["email"] or "").strip(),
        str(student["education"] or "").strip(),
        str(student["mobile_country_code"] or "").strip(),
        str(student["mobile_number"] or "").strip(),
        str(student["profile_photo"] or "").strip(),
    ]
    return any(not value for value in required)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = str(request.form.get("email", "")).strip().lower()
        password = str(request.form.get("password", ""))

        connection = get_db_connection()

        # Email matching is intentionally case-insensitive and ignores
        # accidental spaces copied from mobile/password managers.
        student = connection.execute(
            """
            SELECT *
            FROM students
            WHERE lower(trim(email)) = ?
            LIMIT 1
            """,
            (email,)
        ).fetchone()

        password_valid = False
        legacy_plaintext = False

        if student and password:
            stored_password = str(student["password"] or "").strip()

            try:
                password_valid = check_password_hash(
                    stored_password,
                    password
                )
            except (ValueError, TypeError):
                # Older Civil Career accounts may still contain a
                # plaintext password. Validate once, then upgrade it.
                legacy_plaintext = (
                    stored_password == password
                )
                password_valid = legacy_plaintext

        if student and password_valid:

            if legacy_plaintext:
                connection.execute(
                    """
                    UPDATE students
                    SET password = ?
                    WHERE id = ?
                    """,
                    (
                        generate_password_hash(password),
                        student["id"]
                    )
                )
                connection.commit()

            # LOGIN SUCCESS
            

            # Store student information in session
            session["student_id"] = student["id"]
            session["student_name"] = student["name"]
            session["student_email"] = student["email"]
            session["student_education"] = student["education"]

            if _verification_required(student):
                return redirect(url_for("verify_account"))

            if not student["user_id"]:
                generated_id = _generate_user_id(connection, student["name"])
                connection.execute("UPDATE students SET user_id=? WHERE id=?", (generated_id, student["id"]))
                connection.commit()

            if _profile_incomplete(student):
                connection.close()
                return redirect(url_for("profile", required=1))

            connection.close()
            return redirect(url_for("dashboard"))

        # LOGIN FAILED
        else:

            return render_template(
                "login.html",
                error="Invalid email or password."
            )

    return render_template("login.html")


# ==============================
# STUDENT DASHBOARD
# ==============================

@app.route("/dashboard")
def dashboard():

    # Check whether student is logged in
    if "student_id" not in session:

        return redirect(url_for("login"))


    student_name = session["student_name"]

    student_education = session["student_education"]

    connection = get_db_connection()
    profile_check = connection.execute(
        """SELECT name,email,education,mobile_country_code,mobile_number,profile_photo
           FROM students WHERE id=?""",
        (session["student_id"],)
    ).fetchone()
    preference_check = connection.execute(
        "SELECT target_exam FROM student_preferences WHERE student_id=?",
        (session["student_id"],)
    ).fetchone()
    if _profile_incomplete(profile_check, preference_check["target_exam"] if preference_check else None):
        connection.close()
        return redirect(url_for("profile", required=1))

    verified_jobs = connection.execute(
        """
        SELECT application_last_date, application_last_datetime, exam_date, status
        FROM government_jobs
        WHERE notification_url != '' AND apply_url != '' AND source != ''
        """
    ).fetchall()
    connection.close()
    job_counts = {"NEW": 0, "OPEN": 0, "CLOSING SOON": 0}
    for job in verified_jobs:
        status = government_job_status(
            job["application_last_date"],
            job["exam_date"],
            job["status"],
            job.get("application_last_datetime")
        )
        if status in job_counts:
            job_counts[status] += 1

    matching_jobs = get_matching_jobs(
        session["student_id"],
        limit=3
    )

    connection = get_db_connection()
    progress_row = connection.execute(
        """
        SELECT COALESCE(AVG(percentage), 0) AS overall_progress
        FROM mock_test_results
        WHERE student_id = ?
        """,
        (session["student_id"],)
    ).fetchone()
    connection.close()

    overall_progress = min(
        100,
        round(
            float(
                progress_row["overall_progress"]
                or 0
            )
        )
    )

    return render_template(
        "dashboard.html",
        student_name=student_name,
        student_education=student_education,
        job_counts=job_counts,
        matching_jobs=matching_jobs,
        overall_progress=overall_progress,
    )

# ==============================
# EXAMS
# ==============================

@app.route("/exams")
def exams():

    if "student_id" not in session:

        return redirect(url_for("login"))

    return render_template(
        "exams.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==============================
# DIPLOMA EXAMS
# ==============================

@app.route("/exams/diploma")
def diploma():

    if "student_id" not in session:

        return redirect(url_for("login"))

    return render_template(
        "diploma.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==============================
# B.TECH EXAMS
# ==============================

@app.route("/exams/btech")
def btech():

    if "student_id" not in session:

        return redirect(url_for("login"))

    return render_template(
        "btech.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==============================
# GATE EXAMS
# ==============================

@app.route("/exams/gate")
def gate():

    if "student_id" not in session:

        return redirect(url_for("login"))

    syllabus_year = request.args.get("year", "2027")
    if syllabus_year not in GATE_SYLLABI:
        syllabus_year = "2026"

    return render_template(
        "gate.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        gate_syllabus=GATE_SYLLABI[syllabus_year],
        gate_syllabi=GATE_SYLLABI,
        syllabus_year=syllabus_year
    )

# ==============================
# Government EXAMS
# ==============================

@app.route("/exams/government")
def government():

    if "student_id" not in session:

        return redirect(url_for("login"))

    return render_template(
        "government_exams.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==============================
# GOVERNMENT JOBS
# ==============================

def government_job_status(last_date, exam_date, stored_status, last_datetime=None):
    if stored_status in {"RESULT", "ADMIT CARD", "CANCELLED"}:
        return stored_status

    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    today = now.date()

    try:
        # Use the exact application deadline when available.
        if last_datetime:
            deadline = None
            raw_deadline = str(last_datetime).strip()
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S"):
                try:
                    deadline = datetime.strptime(raw_deadline, fmt).replace(
                        tzinfo=ZoneInfo("Asia/Kolkata")
                    )
                    break
                except ValueError:
                    continue

            if deadline is not None:
                if deadline < now:
                    return "CLOSED"
                if deadline <= now + timedelta(days=7):
                    return "CLOSING SOON"

        # Backward-compatible fallback for older records or malformed datetime values.
        if last_date and (not last_datetime or deadline is None):
            closing = datetime.strptime(str(last_date).strip(), "%Y-%m-%d").date()
            if closing < today:
                return "CLOSED"
            if closing <= today + timedelta(days=7):
                return "CLOSING SOON"

        if exam_date:
            exam = datetime.strptime(str(exam_date).strip(), "%Y-%m-%d").date()
            if exam >= today:
                return "EXAM DATE ANNOUNCED"

    except ValueError:
        return "UNVERIFIED"

    return stored_status if stored_status in {"NEW", "OPEN"} else "UNVERIFIED"


def _normalize_list(raw_value):
    if not raw_value:
        return []
    if isinstance(raw_value, str):
        return [part.strip() for part in raw_value.split(",") if part.strip()]
    return [str(part).strip() for part in raw_value if str(part).strip()]


def get_user_job_preferences(student_id):
    connection = get_db_connection()
    preferences = connection.execute(
        """
        SELECT * FROM user_job_preferences
        WHERE user_id = ?
        """,
        (student_id,)
    ).fetchone()

    if not preferences:
        default_values = {
            "user_id": student_id,
            "qualification": "",
            "branch": "Civil Engineering",
            "preferred_states": "",
            "job_types": "",
            "organizations": "",
            "experience": "Fresher",
            "notifications_enabled": 1,
            "email_enabled": 0,
        }
        connection.execute(
            """
            INSERT INTO user_job_preferences (
                user_id, qualification, branch, preferred_states, job_types,
                organizations, experience, notifications_enabled, email_enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                default_values["user_id"],
                default_values["qualification"],
                default_values["branch"],
                default_values["preferred_states"],
                default_values["job_types"],
                default_values["organizations"],
                default_values["experience"],
                default_values["notifications_enabled"],
                default_values["email_enabled"],
            ),
        )
        connection.commit()
        preferences = dict(default_values)

    connection.close()
    return dict(preferences)


def calculate_match_score(job, preferences):
    if not job or not preferences:
        return 0

    score = 0
    possible = 0

    qualification_pref = (preferences.get("qualification") or "").strip()
    if qualification_pref:
        possible += 35
        job_qualification = (job.get("qualification") or "").lower()
        if qualification_pref.lower() in job_qualification or any(
            item.lower() in job_qualification
            for item in qualification_pref.split("/")
        ):
            score += 35
        elif any(
            item.lower() in job_qualification
            for item in ["diploma", "b.tech", "b.e.", "m.tech", "civil"]
        ):
            score += 20

    branch_pref = (preferences.get("branch") or "").strip()
    if branch_pref:
        possible += 25
        job_branch = (
            job.get("branch")
            or job.get("qualification")
            or ""
        ).lower()
        if (
            "civil" in branch_pref.lower()
            and "civil" in job_branch
        ):
            score += 25
        else:
            score += 10

    states = _normalize_list(preferences.get("preferred_states"))
    if states:
        possible += 15
        job_location = (job.get("job_location") or "").lower()
        if any(state.lower() in job_location for state in states):
            score += 15
        else:
            score += 5

    preferred_job_types = _normalize_list(preferences.get("job_types"))
    if preferred_job_types:
        possible += 15
        job_type = (job.get("job_type") or "").lower()
        if any(
            job_type == item.lower()
            or item.lower() in job_type
            for item in preferred_job_types
        ):
            score += 15
        else:
            score += 5

    experience = (preferences.get("experience") or "").lower()
    if experience:
        possible += 10
        qualification = (job.get("qualification") or "").lower()
        age_limit = (job.get("age_limit") or "").lower()
        if (
            "fresher" in experience
            and (
                "fresher" in qualification
                or "0" in age_limit
            )
        ):
            score += 10
        else:
            score += 5

    if possible == 0:
        return 50

    return min(
        100,
        max(
            0,
            int(round(score / possible * 100))
        )
    )
def get_matching_jobs(student_id, limit=3):
    preferences = get_user_job_preferences(student_id)
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT * FROM government_jobs
        WHERE notification_url != '' AND apply_url != '' AND source != ''
          AND vacancies != ''
          AND qualification != ''
          AND job_role_responsibilities != ''
          AND application_start IS NOT NULL AND application_start != ''
          AND application_last_datetime != ''
          AND (salary != '' OR pay_level != '')
          AND application_fee != ''
        ORDER BY application_last_datetime IS NULL, application_last_datetime ASC
        """
    ).fetchall()
    connection.close()

    matches = []
    for row in rows:
        job = dict(row)
        job["display_status"] = government_job_status(
            job["application_last_date"], job["exam_date"], job["status"]
        )
        # Closed notifications/jobs are not shown in active job matches.
        if job["display_status"] == "CLOSED":
            continue
        job["match_score"] = calculate_match_score(job, preferences)
        if job["match_score"] >= 40:
            matches.append(job)

    matches.sort(key=lambda item: item["match_score"], reverse=True)
    return matches[:limit]


@app.route("/government-jobs/<int:job_id>")
def government_job_detail(job_id):
    if "student_id" not in session:
        return redirect(url_for("login"))
    connection = get_db_connection()
    job = connection.execute(
        """
        SELECT * FROM government_jobs
        WHERE id = ? AND notification_url != '' AND apply_url != '' AND source != ''
          AND vacancies != ''
          AND qualification != ''
          AND job_role_responsibilities != ''
          AND application_start IS NOT NULL AND application_start != ''
          AND application_last_datetime != ''
          AND (salary != '' OR pay_level != '')
          AND application_fee != ''
        """, (job_id,)
    ).fetchone()
    connection.close()
    if not job:
        return "Government job not available", 404
    job = dict(job)
    job["display_status"] = government_job_status(
        job["application_last_date"],
        job["exam_date"],
        job["status"],
        job.get("application_last_datetime")
    )
    # Do not expose closed government-job notifications through direct links.
    if job["display_status"] == "CLOSED":
        return "Government job notification is closed", 404
    preferences = get_user_job_preferences(session["student_id"])
    match_score = calculate_match_score(job, preferences)
    return render_template(
        "government_job_detail.html", job=job,
        student_name=session["student_name"],
        student_education=session["student_education"],
        match_score=match_score,
        user_preferences=preferences
    )


@app.route("/government-jobs/preferences", methods=["GET", "POST"])
def government_jobs_preferences():
    if "student_id" not in session:
        return redirect(url_for("login"))

    student_id = session["student_id"]
    preferences = get_user_job_preferences(student_id)
    message = ""

    if request.method == "POST":
        preferences = {
            "user_id": student_id,
            "qualification": request.form.get("qualification", ""),
            "branch": request.form.get("branch", "Civil Engineering"),
            "preferred_states": request.form.get("preferred_states", ""),
            "job_types": request.form.get("job_types", ""),
            "organizations": request.form.get("organizations", ""),
            "experience": request.form.get("experience", "Fresher"),
            "notifications_enabled": 1 if request.form.get("notifications_enabled") == "on" else 0,
            "email_enabled": 1 if request.form.get("email_enabled") == "on" else 0,
        }

        connection = get_db_connection()
        connection.execute(
            """
            UPDATE user_job_preferences
            SET qualification = ?, branch = ?, preferred_states = ?, job_types = ?,
                organizations = ?, experience = ?, notifications_enabled = ?, email_enabled = ?
            WHERE user_id = ?
            """,
            (
                preferences["qualification"],
                preferences["branch"],
                preferences["preferred_states"],
                preferences["job_types"],
                preferences["organizations"],
                preferences["experience"],
                preferences["notifications_enabled"],
                preferences["email_enabled"],
                student_id,
            ),
        )
        connection.commit()
        connection.close()
        message = "Your job preferences were updated successfully."

    return render_template(
        "government_jobs_preferences.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        preferences=preferences,
        message=message,
    )


@app.route("/government-jobs")
def government_jobs():

    if "student_id" not in session:

        return redirect(url_for("login"))

    filters = {key: request.args.get(key, "").strip() for key in (
        "search", "organization", "qualification", "job_type", "status"
    )}
    connection = get_db_connection()
    jobs = connection.execute(
        """
        SELECT * FROM government_jobs
        WHERE notification_url != '' AND apply_url != '' AND source != ''
          AND vacancies != ''
          AND qualification != ''
          AND job_role_responsibilities != ''
          AND application_start IS NOT NULL AND application_start != ''
          AND application_last_datetime != ''
          AND (salary != '' OR pay_level != '')
          AND application_fee != ''
        ORDER BY application_last_datetime IS NULL, application_last_datetime ASC
        """
    ).fetchall()
    connection.close()
    visible_jobs = []
    counts = {"NEW": 0, "OPEN": 0, "CLOSING SOON": 0}
    matching_jobs = get_matching_jobs(session["student_id"], limit=3)
    user_preferences = get_user_job_preferences(session["student_id"])
    for row in jobs:
        job = dict(row)
        job["display_status"] = government_job_status(
            job["application_last_date"], job["exam_date"], job["status"]
        )
        # Government Jobs page shows only active/open/ongoing notifications.
        if job["display_status"] == "CLOSED":
            continue
        job["match_score"] = calculate_match_score(job, user_preferences)
        searchable = " ".join((job["organization"], job["post_name"], job["department"])).lower()
        if filters["search"] and filters["search"].lower() not in searchable:
            continue
        if filters["organization"] and filters["organization"].lower() not in job["organization"].lower():
            continue
        if filters["qualification"] and filters["qualification"].lower() not in job["qualification"].lower():
            continue
        if filters["job_type"] and filters["job_type"].lower() not in job["job_type"].lower():
            continue
        if filters["status"] and filters["status"] != job["display_status"]:
            continue
        visible_jobs.append(job)
        if job["display_status"] in counts:
            counts[job["display_status"]] += 1

    return render_template(
        "government_jobs.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        jobs=visible_jobs,
        counts=counts,
        filters=filters,
        matching_jobs=matching_jobs,
        user_preferences=user_preferences,
    )

# ==============================
# SYLLABUS
# ==============================

@app.route("/syllabus")
def syllabus():

    if "student_id" not in session:

        return redirect(url_for("login"))

    syllabus_year = request.args.get("year", "2027")
    if syllabus_year not in GATE_SYLLABI:
        syllabus_year = "2026"

    return render_template(
        "syllabus.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        gate_syllabus=GATE_SYLLABI[syllabus_year],
        gate_syllabi=GATE_SYLLABI,
        syllabus_year=syllabus_year
    )


@app.route("/syllabus/gate/<year>/download")
def download_gate_syllabus(year):

    if "student_id" not in session:
        return redirect(url_for("login"))

    if year not in GATE_SYLLABI:
        return "Syllabus year not available", 404

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "SyllabusTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=24, leading=28, textColor=colors.HexColor("#12355B"),
        spaceAfter=6
    )
    subject_style = ParagraphStyle(
        "SyllabusSubject", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=14, leading=17, textColor=colors.HexColor("#12355B"),
        spaceBefore=16, spaceAfter=7
    )
    topic_style = ParagraphStyle(
        "SyllabusTopic", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9.5, leading=13, textColor=colors.HexColor("#334155"),
        leftIndent=8, bulletIndent=0, spaceAfter=5
    )
    label_style = ParagraphStyle(
        "SyllabusLabel", parent=styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=9, leading=12, textColor=colors.HexColor("#64748B")
    )
    small_style = ParagraphStyle(
        "SyllabusSmall", parent=styles["BodyText"], fontSize=9,
        leading=12, textColor=colors.HexColor("#475569")
    )

    pdf_buffer = BytesIO()
    document = SimpleDocTemplate(
        pdf_buffer, pagesize=A4, rightMargin=18 * mm,
        leftMargin=18 * mm, topMargin=25 * mm, bottomMargin=20 * mm,
        title="GATE Civil Engineering Syllabus " + year,
        author="Civil Career"
    )

    def draw_page_chrome(canvas, document):
        canvas.saveState()
        width, height = A4

        # Light diagonal watermark on every PDF page.
        canvas.setFillColor(colors.HexColor("#E5EBF2"))
        canvas.setFont("Helvetica-Bold", 34)
        canvas.translate(width / 2, height / 2)
        canvas.rotate(38)
        canvas.drawCentredString(0, 0, "CIVIL CAREER")
        canvas.setFont("Helvetica", 12)
        canvas.drawCentredString(0, -18, WEBSITE_URL)
        canvas.restoreState()

        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, height - 17 * mm, width - 18 * mm, height - 17 * mm)

        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#12355B"))
        canvas.drawString(18 * mm, height - 12 * mm, "CIVIL CAREER")

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawRightString(
            width - 18 * mm,
            height - 12 * mm,
            "GATE " + year + " | Civil Engineering"
        )

        canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)

        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(colors.HexColor("#12355B"))
        footer_text = "Civil Career | " + WEBSITE_URL
        canvas.drawString(18 * mm, 8 * mm, footer_text)

        # Make the visible website address clickable in PDF viewers.
        website_width = canvas.stringWidth(footer_text, "Helvetica-Bold", 7.5)
        canvas.linkURL(
            WEBSITE_URL,
            (18 * mm, 6 * mm, 18 * mm + website_width, 12 * mm),
            relative=0
        )

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawRightString(
            width - 18 * mm,
            8 * mm,
            "Page " + str(canvas.getPageNumber())
        )
        canvas.restoreState()

    subject_summary = [[
        Paragraph("SECTION", label_style),
        Paragraph("SUBJECT AREA", label_style),
        Paragraph("TOPIC UNITS", label_style),
    ]]
    for number, area in enumerate(GATE_SYLLABI[year], 1):
        subject_summary.append([
            Paragraph(str(number).zfill(2), small_style),
            Paragraph(escape(area["subject"]), small_style),
            Paragraph(str(len(area["topics"])), small_style),
        ])

    content = [
        Spacer(1, 10),
        Paragraph("CIVIL CAREER", label_style),
        Paragraph("GATE Civil Engineering", title_style),
        Paragraph("Master Syllabus | " + escape(year), styles["Heading1"]),
        Spacer(1, 4),
        HRFlowable(width="100%", thickness=2, color=colors.HexColor("#2A9D8F"), spaceAfter=12),
        Paragraph(
            "Website: " + escape(WEBSITE_URL) +
            " | Use this document as the syllabus boundary for Civil Career preparation and mock tests.",
            small_style
        ),
        Spacer(1, 14),
        Table(subject_summary, colWidths=[22 * mm, 105 * mm, 25 * mm], repeatRows=1, style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F1F5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#12355B")),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9E2EC")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ])),
        PageBreak(),
        Paragraph("Syllabus Details", title_style),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2A9D8F"), spaceAfter=8),
    ]
    for number, area in enumerate(GATE_SYLLABI[year], 1):
        content.append(Paragraph(str(number).zfill(2) + "  " + escape(area["subject"]), subject_style))
        for topic in area["topics"]:
            content.append(Paragraph("&#8226; " + escape(topic), topic_style))

    document.build(content, onFirstPage=draw_page_chrome, onLaterPages=draw_page_chrome)
    pdf_buffer.seek(0)
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="GATE-Civil-Syllabus-" + year + ".pdf"
    )

# ==============================
# MATERIALS
# ==============================

@app.route("/materials")
def materials():

    if "student_id" not in session:

        return redirect(url_for("login"))

    return render_template(
        "materials.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==============================
# NOTIFICATIONS
# ==============================

@app.route("/notifications")
def notifications():
    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT id, organization, post_name, application_last_date,
               application_last_datetime, exam_date, notification_url, apply_url, status,
               notification_date
        FROM government_jobs
        WHERE notification_url != ''
          AND apply_url != ''
          AND source != ''
          AND vacancies != ''
          AND qualification != ''
          AND job_role_responsibilities != ''
          AND application_start IS NOT NULL AND application_start != ''
          AND application_last_datetime != ''
          AND (salary != '' OR pay_level != '')
          AND application_fee != ''
        ORDER BY notification_date DESC, id DESC
        LIMIT 20
        """
    ).fetchall()

    alerts = connection.execute(
        """
        SELECT id, category, title, message, link_url, source,
               priority, is_read, created_at
        FROM notification_alerts
        WHERE user_id=?
        ORDER BY is_read ASC, created_at DESC, id DESC
        LIMIT 30
        """,
        (session["student_id"],)
    ).fetchall()

    unread_count = connection.execute(
        "SELECT COUNT(*) AS count FROM notification_alerts WHERE user_id=? AND is_read=0",
        (session["student_id"],)
    ).fetchone()["count"]
    connection.close()

    notification_jobs = []
    for row in rows:
        item = dict(row)
        item["display_status"] = government_job_status(
            item["application_last_date"],
            item["exam_date"],
            item["status"],
            item.get("application_last_datetime")
        )
        # Closed notifications are intentionally hidden from Notifications.
        if item["display_status"] == "CLOSED":
            continue
        notification_jobs.append(item)

    return render_template(
        "notifications.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        notification_jobs=notification_jobs,
        notification_alerts=[dict(row) for row in alerts],
        unread_count=unread_count
    )


@app.route("/notifications/read/<int:alert_id>", methods=["POST"])
def mark_notification_read(alert_id):
    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    connection.execute(
        "UPDATE notification_alerts SET is_read=1 WHERE id=? AND user_id=?",
        (alert_id, session["student_id"])
    )
    connection.commit()
    connection.close()
    return redirect(url_for("notifications"))


@app.route("/notifications/read-all", methods=["POST"])
def mark_all_notifications_read():
    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    connection.execute(
        "UPDATE notification_alerts SET is_read=1 WHERE user_id=?",
        (session["student_id"],)
    )
    connection.commit()
    connection.close()
    return redirect(url_for("notifications"))



# ==============================
# PRACTICE
# ==============================

@app.route("/practice")
def practice():

    if "student_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "practice.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )


# ==============================
# PROFILE
# ==============================

@app.route("/profile-photo/<path:filename>")
def profile_photo(filename):

    if "student_id" not in session:
        return redirect(url_for("login"))

    safe_name = os.path.basename(filename)

    if safe_name != filename:
        return "Invalid file name", 400

    file_path = os.path.join(
        app.config["PROFILE_UPLOAD_FOLDER"],
        safe_name
    )

    if not os.path.isfile(file_path):
        return "Profile image not found", 404

    return send_file(file_path)


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    profile_error = request.args.get("error") or None
    profile_message = request.args.get("message") or None
    required_profile = request.args.get("required") == "1"

    if request.method == "POST":
        action = request.form.get("action", "")

        if action == "personal":
            name = request.form.get("name", "").strip()
            education = request.form.get("education", "").strip()
            if not name or not education:
                profile_error = "Name and education are required."
            else:
                connection.execute("UPDATE students SET name=?, education=? WHERE id=?", (name, education, session["student_id"]))
                connection.commit()
                session["student_name"] = name
                session["student_education"] = education
                profile_message = "Personal details updated successfully."

        elif action == "photo":
            photo = request.files.get("profile_photo")
            allowed_extensions = {"jpg", "jpeg", "png", "webp"}
            extension = os.path.splitext(photo.filename or "")[1].lower().lstrip(".") if photo else ""
            if not photo or not photo.filename:
                profile_error = "Choose a profile photo."
            elif extension not in allowed_extensions:
                profile_error = "Use a JPG, PNG, or WEBP image."
            else:
                os.makedirs(app.config["PROFILE_UPLOAD_FOLDER"], exist_ok=True)
                filename = secure_filename("student-" + str(session["student_id"]) + "-" + uuid.uuid4().hex + "." + extension)
                photo.save(os.path.join(app.config["PROFILE_UPLOAD_FOLDER"], filename))
                connection.execute("UPDATE students SET profile_photo=? WHERE id=?", (filename, session["student_id"]))
                connection.commit()
                profile_message = "Profile photo updated successfully."

    student = connection.execute(
        """SELECT id,user_id,name,email,education,profile_photo,mobile_country_code,mobile_number,
                  email_verified,mobile_verified
           FROM students WHERE id=?""",
        (session["student_id"],)
    ).fetchone()
    connection.close()

    if student and not student["user_id"]:
        connection = get_db_connection()
        generated_id = _generate_user_id(connection, student["name"])
        connection.execute("UPDATE students SET user_id=? WHERE id=?", (generated_id, student["id"]))
        connection.commit()
        connection.close()
        student = dict(student)
        student["user_id"] = generated_id

    complete = not _profile_incomplete(student)

    return render_template(
        "profile.html",
        user_id=student["user_id"] if student else "",
        student_name=student["name"] if student else "",
        student_education=student["education"] if student else "",
        student_email=student["email"] if student else "",
        mobile_country_code=student["mobile_country_code"] if student else "",
        mobile_number=student["mobile_number"] if student else "",
        email_verified=int(student["email_verified"] or 0) if student else 0,
        mobile_verified=int(student["mobile_verified"] or 0) if student else 0,
        profile_photo=student["profile_photo"] if student else None,
        profile_error=profile_error,
        profile_message=profile_message,
        required_profile=required_profile,
        profile_complete=complete
    )



# ==========================================
# MOCK TEST HISTORY DETAILS
# ==========================================

@app.route("/mock-test-history/<int:result_id>")
def mock_test_history(result_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    result = connection.execute(
        """
        SELECT
            id,
            exam_slug,
            exam_name,
            total_questions,
            correct,
            wrong,
            unanswered,
            score,
            percentage,
            attempt_id,
            created_at
        FROM mock_test_results
        WHERE id = ?
          AND student_id = ?
        """,
        (
            result_id,
            session["student_id"]
        )
    ).fetchone()

    connection.close()

    if result is None:
        return "Mock test result not found", 404

    return render_template(
        "mock_history_details.html",

        student_name=session["student_name"],

        student_education=session["student_education"],

        result=result
    )

# ==============================
# MCQ PRACTICE
# ==============================

MCQ_QUESTIONS = [

    {
        "question": "What is the SI unit of force?",
        "option_a": "Newton",
        "option_b": "Pascal",
        "option_c": "Joule",
        "option_d": "Watt",
        "correct_answer": "A"
    },

    {
        "question": "Which instrument is commonly used for measuring horizontal angles in surveying?",
        "option_a": "Level",
        "option_b": "Theodolite",
        "option_c": "Staff",
        "option_d": "Planimeter",
        "correct_answer": "B"
    },

    {
        "question": "The main purpose of curing concrete is to:",
        "option_a": "Increase its weight",
        "option_b": "Maintain moisture for hydration",
        "option_c": "Reduce cement content",
        "option_d": "Increase aggregate size",
        "correct_answer": "B"
    },

    {
        "question": "Which type of foundation is generally used when good soil is available near the ground surface?",
        "option_a": "Deep foundation",
        "option_b": "Pile foundation",
        "option_c": "Shallow foundation",
        "option_d": "Caisson foundation",
        "correct_answer": "C"
    },

    {
        "question": "Which material is primarily responsible for binding aggregates in concrete?",
        "option_a": "Cement",
        "option_b": "Sand",
        "option_c": "Coarse aggregate",
        "option_d": "Water only",
        "correct_answer": "A"
    }

]


@app.route("/mcq", methods=["GET", "POST"])
def mcq():

    if "student_id" not in session:
        return redirect(url_for("login"))

    if "mcq_index" not in session:
        session["mcq_index"] = 0

    if "mcq_score" not in session:
        session["mcq_score"] = 0

    result = None

    if request.method == "POST":

        index = session["mcq_index"]

        question = MCQ_QUESTIONS[index]

        answer = request.form.get("answer")

        if answer == question["correct_answer"]:

            result = "Correct"

            session["mcq_score"] += 1

        else:

            result = "Wrong"


        return render_template(

            "mcq.html",

            student_name=session["student_name"],

            student_education=session["student_education"],

            question=question,

            question_number=index + 1,

            score=session["mcq_score"],

            result=result

        )


    index = session["mcq_index"]

    question = MCQ_QUESTIONS[index]

    return render_template(

        "mcq.html",

        student_name=session["student_name"],

        student_education=session["student_education"],

        question=question,

        question_number=index + 1,

        score=session["mcq_score"],

        result=None

    )


@app.route("/mcq/next")
def mcq_next():

    if "student_id" not in session:
        return redirect(url_for("login"))

    session["mcq_index"] += 1

    if session["mcq_index"] >= len(MCQ_QUESTIONS):

        session["mcq_index"] = 0

        session["mcq_score"] = 0

    return redirect(url_for("mcq"))

# ==============================
# SUBJECT PRACTICE
# ==============================

@app.route("/subject-practice")
def subject_practice():

    if "student_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "subject_practice.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==========================================
# SUBJECT QUESTION BANK
# ==========================================

SUBJECT_QUESTIONS = {

    "engineering-mathematics": [
    
            {
                "question": "What is the derivative of x² with respect to x?",
    
                "option_a": "x",
    
                "option_b": "2x",
    
                "option_c": "x²",
    
                "option_d": "2",
    
                "correct_answer": "B"
            },
    
            {
                "question": "The value of sin 90° is:",
    
                "option_a": "0",
    
                "option_b": "1",
    
                "option_c": "-1",
    
                "option_d": "1/2",
    
                "correct_answer": "B"
            },
    
            {
                "question": "The integral of 1 dx is:",
    
                "option_a": "0",
    
                "option_b": "x + C",
    
                "option_c": "1 + C",
    
                "option_d": "x² + C",
    
                "correct_answer": "B"
            },
    
            {
                "question": "A matrix having equal number of rows and columns is called:",
    
                "option_a": "Rectangular matrix",
    
                "option_b": "Row matrix",
    
                "option_c": "Square matrix",
    
                "option_d": "Column matrix",
    
                "correct_answer": "C"
            },
    
            {
                "question": "The determinant of an identity matrix is:",
    
                "option_a": "0",
    
                "option_b": "1",
    
                "option_c": "2",
    
                "option_d": "Depends on its order",
    
                "correct_answer": "B"
            }
    
        ],

    "strength-of-materials": [

        {
            "question": "Stress is defined as:",

            "option_a": "Load per unit area",

            "option_b": "Area per unit load",

            "option_c": "Load multiplied by area",

            "option_d": "Change in length",

            "correct_answer": "A"
        },

        {
            "question": "The SI unit of stress is:",

            "option_a": "Newton",

            "option_b": "Pascal",

            "option_c": "Joule",

            "option_d": "Watt",

            "correct_answer": "B"
        },

        {
            "question": "Strain is a:",

            "option_a": "Dimensional quantity",

            "option_b": "Dimensionless quantity",

            "option_c": "Force",

            "option_d": "Moment",

            "correct_answer": "B"
        },

        {
            "question": "Young's modulus is the ratio of:",

            "option_a": "Shear stress to shear strain",

            "option_b": "Normal stress to normal strain",

            "option_c": "Load to area",

            "option_d": "Moment to curvature",

            "correct_answer": "B"
        },

        {
            "question": "The bending moment at a simple support of a simply supported beam is generally:",

            "option_a": "Maximum",

            "option_b": "Minimum but not zero",

            "option_c": "Zero",

            "option_d": "Infinite",

            "correct_answer": "C"
        },

        {
            "question": "The neutral axis of a homogeneous beam passes through its:",

            "option_a": "Top surface",

            "option_b": "Bottom surface",

            "option_c": "Centroid",

            "option_d": "Support",

            "correct_answer": "C"
        },

        {
            "question": "Poisson's ratio is the ratio of:",

            "option_a": "Longitudinal strain to lateral strain",

            "option_b": "Lateral strain to longitudinal strain",

            "option_c": "Stress to strain",

            "option_d": "Load to displacement",

            "correct_answer": "B"
        },

        {
            "question": "Torsion in a circular shaft produces primarily:",

            "option_a": "Tensile stress",

            "option_b": "Compressive stress",

            "option_c": "Shear stress",

            "option_d": "Bearing stress",

            "correct_answer": "C"
        }

    ],

       "concrete-technology": [

        {
            "question": "The main binding material in ordinary concrete is:",

            "option_a": "Sand",
            "option_b": "Cement",
            "option_c": "Coarse aggregate",
            "option_d": "Brick",

            "correct_answer": "B"
        },

        {
            "question": "The process of maintaining adequate moisture in concrete is called:",

            "option_a": "Compaction",
            "option_b": "Curing",
            "option_c": "Mixing",
            "option_d": "Batching",

            "correct_answer": "B"
        },

        {
            "question": "The workability of concrete is commonly measured by:",

            "option_a": "Slump test",
            "option_b": "Impact test",
            "option_c": "Tensile test",
            "option_d": "Bending test",

            "correct_answer": "A"
        },

        {
            "question": "A lower water-cement ratio generally produces:",

            "option_a": "Lower strength",
            "option_b": "Higher strength",
            "option_c": "No concrete",
            "option_d": "Only more bleeding",

            "correct_answer": "B"
        },

        {
            "question": "The approximate specific gravity of ordinary Portland cement is:",

            "option_a": "1.0",
            "option_b": "2.0",
            "option_c": "3.15",
            "option_d": "5.0",

            "correct_answer": "C"
        }

    ],


    "structural-engineering": [

        {
            "question": "RCC stands for:",

            "option_a": "Reinforced Cement Concrete",
            "option_b": "Ready Cement Construction",
            "option_c": "Road Construction Concrete",
            "option_d": "Reinforced Clay Concrete",

            "correct_answer": "A"
        },

        {
            "question": "Steel reinforcement in RCC mainly resists:",

            "option_a": "Tension",
            "option_b": "Only temperature",
            "option_c": "Water pressure",
            "option_d": "Dead load only",

            "correct_answer": "A"
        },

        {
            "question": "A beam primarily carries:",

            "option_a": "Axial compression only",
            "option_b": "Bending and shear",
            "option_c": "Temperature only",
            "option_d": "Water flow",

            "correct_answer": "B"
        },

        {
            "question": "A column is primarily designed to resist:",

            "option_a": "Axial load",
            "option_b": "Water pressure",
            "option_c": "Soil erosion",
            "option_d": "Traffic flow",

            "correct_answer": "A"
        },

        {
            "question": "The permanent load of a structure is called:",

            "option_a": "Live load",
            "option_b": "Dead load",
            "option_c": "Impact load",
            "option_d": "Wind load",

            "correct_answer": "B"
        }

    ],


    "geotechnical": [

        {
            "question": "The study of soil as an engineering material is called:",

            "option_a": "Hydrology",
            "option_b": "Geotechnical engineering",
            "option_c": "Surveying",
            "option_d": "Transportation engineering",

            "correct_answer": "B"
        },

        {
            "question": "The void ratio of soil is defined as:",

            "option_a": "Volume of solids / volume of voids",
            "option_b": "Volume of voids / volume of solids",
            "option_c": "Volume of water / volume of soil",
            "option_d": "Volume of air / volume of water",

            "correct_answer": "B"
        },

        {
            "question": "The bearing capacity of soil is important in the design of:",

            "option_a": "Foundations",
            "option_b": "Road signs",
            "option_c": "Water tanks only",
            "option_d": "Survey instruments",

            "correct_answer": "A"
        },

        {
            "question": "A foundation that transfers load through piles is called:",

            "option_a": "Shallow foundation",
            "option_b": "Deep foundation",
            "option_c": "Strip foundation",
            "option_d": "Isolated footing",

            "correct_answer": "B"
        },

        {
            "question": "The water content of soil is generally expressed as the ratio of:",

            "option_a": "Weight of water to weight of solids",
            "option_b": "Weight of solids to weight of water",
            "option_c": "Volume of soil to volume of water",
            "option_d": "Weight of air to weight of soil",

            "correct_answer": "A"
        }

    ],


    "fluid-mechanics": [

        {
            "question": "The SI unit of pressure is:",

            "option_a": "Newton",
            "option_b": "Pascal",
            "option_c": "Joule",
            "option_d": "Watt",

            "correct_answer": "B"
        },

        {
            "question": "The density of water is approximately:",

            "option_a": "100 kg/m³",
            "option_b": "500 kg/m³",
            "option_c": "1000 kg/m³",
            "option_d": "2000 kg/m³",

            "correct_answer": "C"
        },

        {
            "question": "Bernoulli's equation is based on conservation of:",

            "option_a": "Mass only",
            "option_b": "Energy",
            "option_c": "Temperature",
            "option_d": "Momentum only",

            "correct_answer": "B"
        },

        {
            "question": "The viscosity of a fluid represents its resistance to:",

            "option_a": "Flow",
            "option_b": "Gravity",
            "option_c": "Temperature",
            "option_d": "Pressure only",

            "correct_answer": "A"
        },

        {
            "question": "Water flowing through a pipe is an example of:",

            "option_a": "Fluid flow",
            "option_b": "Solid deformation",
            "option_c": "Soil consolidation",
            "option_d": "Structural buckling",

            "correct_answer": "A"
        }

    ],


    "transportation": [

        {
            "question": "The primary purpose of a pavement is to:",

            "option_a": "Carry traffic safely",
            "option_b": "Store water",
            "option_c": "Support buildings",
            "option_d": "Measure rainfall",

            "correct_answer": "A"
        },

        {
            "question": "The camber of a road is provided mainly for:",

            "option_a": "Drainage",
            "option_b": "Increasing traffic",
            "option_c": "Reducing road width",
            "option_d": "Increasing vehicle weight",

            "correct_answer": "A"
        },

        {
            "question": "Traffic volume is generally expressed as:",

            "option_a": "Vehicles per unit time",
            "option_b": "Metres per second only",
            "option_c": "Tonnes per metre",
            "option_d": "Litres per second",

            "correct_answer": "A"
        },

        {
            "question": "A road curve provided to gradually introduce superelevation is called:",

            "option_a": "Transition curve",
            "option_b": "Vertical curve only",
            "option_c": "Circular curve only",
            "option_d": "Simple tangent",

            "correct_answer": "A"
        },

        {
            "question": "The surface layer of a flexible pavement is generally called:",

            "option_a": "Wearing course",
            "option_b": "Subgrade",
            "option_c": "Subsoil",
            "option_d": "Foundation soil",

            "correct_answer": "A"
        }

    ],


    "environmental": [

        {
            "question": "The main purpose of water treatment is to:",

            "option_a": "Make water suitable for its intended use",
            "option_b": "Increase pollution",
            "option_c": "Increase soil strength",
            "option_d": "Produce cement",

            "correct_answer": "A"
        },

        {
            "question": "BOD stands for:",

            "option_a": "Biochemical Oxygen Demand",
            "option_b": "Basic Oxygen Density",
            "option_c": "Biological Organic Drainage",
            "option_d": "Base Oxygen Demand",

            "correct_answer": "A"
        },

        {
            "question": "Chlorination of water is mainly used for:",

            "option_a": "Disinfection",
            "option_b": "Increasing hardness",
            "option_c": "Removing sand only",
            "option_d": "Increasing turbidity",

            "correct_answer": "A"
        },

        {
            "question": "A sewer is used to carry:",

            "option_a": "Wastewater",
            "option_b": "Concrete",
            "option_c": "Cement",
            "option_d": "Fresh air",

            "correct_answer": "A"
        },

        {
            "question": "Air pollution refers to the presence of harmful substances in:",

            "option_a": "Atmosphere",
            "option_b": "Concrete",
            "option_c": "Steel",
            "option_d": "Foundation",

            "correct_answer": "A"
        }

    ],


    "surveying": [

        {
            "question": "Surveying is primarily concerned with determining:",

            "option_a": "Relative positions of points",
            "option_b": "Concrete strength only",
            "option_c": "Soil chemistry only",
            "option_d": "Water quality only",

            "correct_answer": "A"
        },

        {
            "question": "A theodolite is used mainly for measuring:",

            "option_a": "Angles",
            "option_b": "Temperature",
            "option_c": "Water pressure",
            "option_d": "Concrete strength",

            "correct_answer": "A"
        },

        {
            "question": "Levelling is used to determine:",

            "option_a": "Difference in elevation",
            "option_b": "Cement content",
            "option_c": "Traffic volume",
            "option_d": "Soil colour",

            "correct_answer": "A"
        },

        {
            "question": "A benchmark in surveying is a point of known:",

            "option_a": "Elevation",
            "option_b": "Traffic volume",
            "option_c": "Concrete grade",
            "option_d": "Soil density",

            "correct_answer": "A"
        },

        {
            "question": "A total station combines electronic measurement with:",

            "option_a": "Data processing",
            "option_b": "Concrete mixing",
            "option_c": "Soil compaction",
            "option_d": "Water treatment",

            "correct_answer": "A"
        }

    ],


    "construction-materials": [

        {
            "question": "The main raw material used in ordinary Portland cement manufacture is:",

            "option_a": "Limestone",
            "option_b": "Timber",
            "option_c": "Bitumen",
            "option_d": "Glass",

            "correct_answer": "A"
        },

        {
            "question": "A good building brick should have:",

            "option_a": "Good strength",
            "option_b": "Very high water absorption",
            "option_c": "Irregular shape",
            "option_d": "Poor durability",

            "correct_answer": "A"
        },

        {
            "question": "Timber is obtained mainly from:",

            "option_a": "Trees",
            "option_b": "Rocks",
            "option_c": "Clay",
            "option_d": "Limestone",

            "correct_answer": "A"
        },

        {
            "question": "Bitumen is commonly used in:",

            "option_a": "Road construction",
            "option_b": "Water purification",
            "option_c": "Brick burning",
            "option_d": "Survey instruments",

            "correct_answer": "A"
        },

        {
            "question": "Steel is an alloy primarily consisting of iron and:",

            "option_a": "Carbon",
            "option_b": "Sand",
            "option_c": "Cement",
            "option_d": "Timber",

            "correct_answer": "A"
        }

    ],

    "construction-management": [

        {
            "question": "In a construction project network, the critical path is the path with:",
            "option_a": "The maximum total float",
            "option_b": "The minimum duration",
            "option_c": "Zero total float",
            "option_d": "Only independent activities",
            "correct_answer": "C"
        },

        {
            "question": "In PERT, the expected time of an activity is calculated using:",
            "option_a": "Only the most likely time",
            "option_b": "A weighted average of three time estimates",
            "option_c": "The optimistic time only",
            "option_d": "The pessimistic time only",
            "correct_answer": "B"
        },

        {
            "question": "The center line method of estimation is most suitable when:",
            "option_a": "Wall thicknesses are highly irregular",
            "option_b": "The plan is symmetrical and walls are uniform",
            "option_c": "Only excavation quantities are required",
            "option_d": "No drawings are available",
            "correct_answer": "B"
        },

        {
            "question": "A contract in which the contractor is paid an agreed fixed amount for the completed work is a:",
            "option_a": "Lump-sum contract",
            "option_b": "Cost-plus contract",
            "option_c": "Piece-rate contract",
            "option_d": "Labour-only contract",
            "correct_answer": "A"
        },

        {
            "question": "Which equipment is primarily used for lifting and placing materials at elevated locations?",
            "option_a": "Scraper",
            "option_b": "Tower crane",
            "option_c": "Motor grader",
            "option_d": "Roller",
            "correct_answer": "B"
        }

    ],

}

# ==========================================
# PREVIOUS YEAR QUESTIONS
# ==========================================

@app.route("/pyqs")
def pyqs():

    if "student_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "pyqs.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==========================================
# PYQ QUESTION BANK
# ==========================================

PYQ_QUESTIONS = {

    "gate": [

        {
            "question": "For a simply supported beam carrying a central point load, the maximum bending moment occurs at:",

            "option_a": "Left support",
            "option_b": "Right support",
            "option_c": "Centre of the beam",
            "option_d": "Quarter span",

            "correct_answer": "C"
        },

        {
            "question": "The unit weight of water is approximately:",

            "option_a": "1 kN/m³",
            "option_b": "9.81 kN/m³",
            "option_c": "98.1 kN/m³",
            "option_d": "100 kN/m³",

            "correct_answer": "B"
        },

        {
            "question": "In a homogeneous soil, effective stress is equal to total stress minus:",

            "option_a": "Earth pressure",
            "option_b": "Pore water pressure",
            "option_c": "Shear stress",
            "option_d": "Overburden pressure",

            "correct_answer": "B"
        },

        {
            "question": "The coefficient of permeability has the dimensions of:",

            "option_a": "Length",
            "option_b": "Time",
            "option_c": "Length per unit time",
            "option_d": "Force",

            "correct_answer": "C"
        },

        {
            "question": "The Reynolds number is used to determine the nature of:",

            "option_a": "Soil",
            "option_b": "Concrete",
            "option_c": "Fluid flow",
            "option_d": "Road pavement",

            "correct_answer": "C"
        }

    ],


    "ssc-je": [

        {
            "question": "The slump test is used to determine the workability of:",

            "option_a": "Steel",
            "option_b": "Concrete",
            "option_c": "Soil",
            "option_d": "Bitumen",

            "correct_answer": "B"
        },

        {
            "question": "The primary function of reinforcement in RCC beams is to resist:",

            "option_a": "Tension",
            "option_b": "Water pressure",
            "option_c": "Temperature only",
            "option_d": "Dead weight only",

            "correct_answer": "A"
        },

        {
            "question": "A contour line joins points having equal:",

            "option_a": "Temperature",
            "option_b": "Elevation",
            "option_c": "Pressure",
            "option_d": "Distance",

            "correct_answer": "B"
        },

        {
            "question": "The main purpose of providing camber on a road is:",

            "option_a": "Drainage",
            "option_b": "Increasing road length",
            "option_c": "Reducing traffic",
            "option_d": "Increasing pavement thickness",

            "correct_answer": "A"
        },

        {
            "question": "The unit of discharge is:",

            "option_a": "m",
            "option_b": "m²",
            "option_c": "m³/s",
            "option_d": "N/m²",

            "correct_answer": "C"
        }

    ],


    "je-ae": [

        {
            "question": "The bearing capacity of soil is mainly important for the design of:",

            "option_a": "Foundations",
            "option_b": "Road signs",
            "option_c": "Survey instruments",
            "option_d": "Water meters",

            "correct_answer": "A"
        },

        {
            "question": "The neutral axis of a homogeneous beam passes through its:",

            "option_a": "Top surface",
            "option_b": "Centroid",
            "option_c": "Bottom surface",
            "option_d": "Support",

            "correct_answer": "B"
        },

        {
            "question": "The process of maintaining moisture in freshly placed concrete is called:",

            "option_a": "Compaction",
            "option_b": "Curing",
            "option_c": "Batching",
            "option_d": "Mixing",

            "correct_answer": "B"
        },

        {
            "question": "A theodolite is primarily used for measuring:",

            "option_a": "Angles",
            "option_b": "Temperature",
            "option_c": "Concrete strength",
            "option_d": "Soil moisture",

            "correct_answer": "A"
        },

        {
            "question": "Bernoulli's theorem is based on conservation of:",

            "option_a": "Mass",
            "option_b": "Energy",
            "option_c": "Temperature",
            "option_d": "Volume",

            "correct_answer": "B"
        }

    ],


    "diploma": [

        {
            "question": "The SI unit of force is:",

            "option_a": "Pascal",
            "option_b": "Newton",
            "option_c": "Joule",
            "option_d": "Watt",

            "correct_answer": "B"
        },

        {
            "question": "The main constituent of ordinary Portland cement is:",

            "option_a": "Cement clinker",
            "option_b": "Timber",
            "option_c": "Bitumen",
            "option_d": "Glass",

            "correct_answer": "A"
        },

        {
            "question": "Levelling is used to determine:",

            "option_a": "Difference in elevation",
            "option_b": "Concrete grade",
            "option_c": "Traffic volume",
            "option_d": "Water quality",

            "correct_answer": "A"
        },

        {
            "question": "A foundation transfers structural load to the:",

            "option_a": "Roof",
            "option_b": "Soil",
            "option_c": "Window",
            "option_d": "Ceiling",

            "correct_answer": "B"
        },

        {
            "question": "The process of removing air voids from freshly placed concrete is called:",

            "option_a": "Curing",
            "option_b": "Compaction",
            "option_c": "Hydration",
            "option_d": "Segregation",

            "correct_answer": "B"
        }

    ],


    "btech": [

        {
            "question": "Young's modulus is the ratio of:",

            "option_a": "Normal stress to normal strain",
            "option_b": "Shear stress to shear strain",
            "option_c": "Load to area",
            "option_d": "Moment to force",

            "correct_answer": "A"
        },

        {
            "question": "For a simply supported beam, the bending moment at an ideal simple support is:",

            "option_a": "Maximum",
            "option_b": "Zero",
            "option_c": "Infinite",
            "option_d": "Negative infinity",

            "correct_answer": "B"
        },

        {
            "question": "The Reynolds number is a dimensionless parameter used in:",

            "option_a": "Fluid mechanics",
            "option_b": "Surveying only",
            "option_c": "Concrete mix design only",
            "option_d": "Building estimation only",

            "correct_answer": "A"
        },

        {
            "question": "Effective stress in saturated soil is equal to:",

            "option_a": "Total stress + pore pressure",
            "option_b": "Total stress − pore pressure",
            "option_c": "Pore pressure − total stress",
            "option_d": "Total stress × pore pressure",

            "correct_answer": "B"
        },

        {
            "question": "The main purpose of a transition curve in highway engineering is to:",

            "option_a": "Gradually introduce curvature",
            "option_b": "Increase pavement thickness",
            "option_c": "Remove drainage",
            "option_d": "Reduce road width",

            "correct_answer": "A"
        }

    ],


    "government": [

        {
            "question": "Which test is commonly used to determine the consistency of cement paste?",

            "option_a": "Vicat test",
            "option_b": "Slump test",
            "option_c": "Proctor test",
            "option_d": "CBR test",

            "correct_answer": "A"
        },

        {
            "question": "CBR is commonly associated with:",

            "option_a": "Highway engineering",
            "option_b": "Structural steel",
            "option_c": "Water treatment",
            "option_d": "Surveying",

            "correct_answer": "A"
        },

        {
            "question": "The main purpose of a retaining wall is to retain:",

            "option_a": "Soil",
            "option_b": "Concrete",
            "option_c": "Steel",
            "option_d": "Water only",

            "correct_answer": "A"
        },

        {
            "question": "The unit weight of water is approximately:",

            "option_a": "0.981 kN/m³",
            "option_b": "9.81 kN/m³",
            "option_c": "98.1 kN/m³",
            "option_d": "981 kN/m³",

            "correct_answer": "B"
        },

        {
            "question": "A total station is an instrument used in:",

            "option_a": "Surveying",
            "option_b": "Concrete curing",
            "option_c": "Soil compaction",
            "option_d": "Water treatment",

            "correct_answer": "A"
        }

    ]

}

# ==========================================
# PYQ EXAM ROUTES
# ==========================================

@app.route("/pyqs/<exam_slug>",
           methods=["GET", "POST"])
def pyq_exam(exam_slug):

    if "student_id" not in session:
        return redirect(url_for("login"))

    if exam_slug not in PYQ_QUESTIONS:
        return "PYQ exam not available", 404

    questions = PYQ_QUESTIONS[exam_slug]

    index_key = "pyq_index_" + exam_slug

    score_key = "pyq_score_" + exam_slug

    if index_key not in session:
        session[index_key] = 0

    if score_key not in session:
        session[score_key] = 0

    index = session[index_key]

    if index >= len(questions):

        index = 0

        session[index_key] = 0

        session[score_key] = 0

    question = questions[index]

    result = None

    if request.method == "POST":

        answer = request.form.get("answer")

        if answer == question["correct_answer"]:

            result = "Correct"

            session[score_key] += 1

        else:

            result = "Wrong"

    exam_names = {

    "gate": "GATE",

    "ssc-je": "SSC JE",

    "je-ae": "JE / AE",

    "diploma": "Diploma",

    "btech": "B.Tech Civil",

    "government": "Government Exams"

}

    exam_name = exam_names.get(
        exam_slug,
        exam_slug.replace("-", " ").upper()
    )

    return render_template(

        "pyq_exam.html",

        student_name=session["student_name"],

        student_education=session["student_education"],

        exam_name=exam_name,

        exam_slug=exam_slug,

        question=question,

        question_number=index + 1,

        total_questions=len(questions),

        score=session[score_key],

        result=result

    )


@app.route("/pyqs/<exam_slug>/next")
def pyq_exam_next(exam_slug):

    if "student_id" not in session:
        return redirect(url_for("login"))

    if exam_slug not in PYQ_QUESTIONS:
        return "PYQ exam not available", 404

    index_key = "pyq_index_" + exam_slug

    score_key = "pyq_score_" + exam_slug

    if index_key not in session:
        session[index_key] = 0

    if score_key not in session:
        session[score_key] = 0

    session[index_key] += 1

    if session[index_key] >= len(
        PYQ_QUESTIONS[exam_slug]
    ):

        session[index_key] = 0

        session[score_key] = 0

    return redirect(
        url_for(
            "pyq_exam",
            exam_slug=exam_slug
        )
    )

# ==========================================#
# MOCK TEST SELECTION
# ==========================================

@app.route("/mock-tests")
def mock_tests():

    if "student_id" not in session:
        return redirect(url_for("login"))

    return render_template(
        "mock_tests.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )

# ==========================================
# MOCK TEST QUESTION BANK
# ==========================================

MOCK_TEST_QUESTIONS = {

    "gate": [

        {
            "question":
                "For a simply supported beam with a central point load, the maximum bending moment occurs at:",

            "option_a": "Left support",
            "option_b": "Right support",
            "option_c": "Centre of the beam",
            "option_d": "Quarter span",

            "correct_answer": "C"
        },
