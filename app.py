from flask import Flask, render_template, request, redirect, url_for, session, send_file, jsonify, abort
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

def draw_civilcareer_pdf_chrome(canvas, document, header_right="CIVIL CAREER", footer_label="Civil Career"):
    """Common Civil Career PDF watermark, header and footer used by every generated PDF."""
    canvas.saveState()
    width, height = A4

    # Diagonal brand watermark on every page.
    canvas.saveState()
    canvas.setFillColor(colors.HexColor("#E7EDF3"))
    canvas.setFont("Helvetica-Bold", 38)
    canvas.translate(width / 2, height / 2)
    canvas.rotate(38)
    canvas.drawCentredString(0, 0, "CIVIL CAREER")
    canvas.setFont("Helvetica", 10)
    canvas.drawCentredString(0, -17, PDF_WEBSITE_URL)
    canvas.restoreState()

    # Header.
    canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
    canvas.setLineWidth(0.6)
    canvas.line(18 * mm, height - 17 * mm, width - 18 * mm, height - 17 * mm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.HexColor("#12355B"))
    canvas.drawString(18 * mm, height - 12 * mm, "CIVIL CAREER")
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawRightString(width - 18 * mm, height - 12 * mm, str(header_right))

    # Footer: date/time + test/document + website on left, page number on right.
    canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
    timestamp = datetime.now(IST_ZONE).strftime("%d %b %Y, %I:%M %p IST")
    footer_text = "%s  |  %s  |  %s" % (timestamp, str(footer_label), PDF_WEBSITE_URL)
    canvas.setFont("Helvetica", 7.2)
    canvas.setFillColor(colors.HexColor("#475569"))
    canvas.drawString(18 * mm, 8 * mm, footer_text)
    website_start = footer_text.rfind(PDF_WEBSITE_URL)
    website_x = 18 * mm + canvas.stringWidth(footer_text[:website_start], "Helvetica", 7.2)
    website_w = canvas.stringWidth(PDF_WEBSITE_URL, "Helvetica", 7.2)
    canvas.linkURL(PDF_WEBSITE_URL, (website_x, 6 * mm, website_x + website_w, 11 * mm), relative=0)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.setFillColor(colors.HexColor("#12355B"))
    canvas.drawRightString(width - 18 * mm, 8 * mm, "Page %d" % document.page)
    canvas.restoreState()

from gate_mock_engine import GATE_SYLLABI, GATE_SYLLABUS, build_gate_mock, next_difficulty_mode, _question_fingerprint

app = Flask(__name__)

@app.after_request
def add_site_date_formatter(response):
    """Load the date display formatter on all HTML pages without changing stored/input dates."""
    if response.mimetype == "text/html":
        html = response.get_data(as_text=True)

        # Keep the production Railway URL consistent everywhere in rendered HTML.
        html = html.replace("https://civilcareer.com", WEBSITE_URL)
        html = html.replace("http://civilcareer.com", WEBSITE_URL)

        script_tag = '<script src="/static/js/date-format.js?v=20260927a" defer></script>'
        if "</body>" in html and "date-format.js" not in html:
            html = html.replace("</body>", script_tag + "</body>")
        response.set_data(html)
    return response



@app.template_filter("date_dmy")
def format_date_dmy(value):
    """Display stored timestamps in Indian Standard Time (IST)."""
    if value is None or value == "":
        return "Not announced"
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime("%d-%m-%Y")
    formatted = format_datetime_ist(value)
    return formatted if formatted != "Not available" else "Not announced"


WEBSITE_URL = "https://civilcareer.up.railway.app"

# Canonical public URL used across student-facing pages and generated PDFs.
PDF_WEBSITE_URL = "https://civilcareer.up.railway.app"

IST_ZONE = ZoneInfo("Asia/Kolkata")

def format_datetime_ist(value, include_seconds=False):
    """Format stored UTC timestamps as Indian Standard Time for student-facing history/PDFs."""
    if value is None or value == "":
        return "Not available"
    if isinstance(value, datetime):
        dt = value
    else:
        text_value = str(value).strip()
        try:
            dt = datetime.fromisoformat(text_value.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return text_value
    # Stored naive database timestamps are UTC; convert them to IST for display.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    dt = dt.astimezone(IST_ZONE)
    fmt = "%d-%m-%Y %I:%M:%S %p IST" if include_seconds else "%d-%m-%Y %I:%M %p IST"
    return dt.strftime(fmt)


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
app.config["PERMANENT_SESSION_LIFETIME"] = 1800
app.config["SESSION_REFRESH_EACH_REQUEST"] = True

# Keep large mock-test answer/question state server-side. Flask's default
# cookie session can exceed browser cookie limits, causing subsequent PDF
# requests to lose the login session and redirect to the login HTML page.
from flask_session import Session

app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = os.path.join(DATA_DIR, "flask_sessions")
app.config["SESSION_FILE_THRESHOLD"] = 1000
app.config["SESSION_USE_SIGNER"] = True
os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
Session(app)


@app.before_request
def enforce_session_idle_timeout():
    if "student_id" not in session:
        return None
    now = int(time.time())
    last_activity = int(session.get("last_activity", now))
    if now - last_activity >= 1800:
        session.clear()
        return redirect(url_for("login", expired=1))
    if request.endpoint != "static":
        session["last_activity"] = now
    session.permanent = True
    return None

# =========================================================
# GLOBAL AUTHENTICATED NAVIGATION
# Keep the application pages full-width and provide one
# compact menu button in the top-left instead of a permanent
# sidebar on every page.
# =========================================================

@app.context_processor
def inject_current_profile_photo():
    """Make the logged-in student's saved photo available to page templates."""
    if "student_id" not in session:
        return {"profile_photo": None}
    connection = None
    try:
        connection = get_db_connection()
        row = connection.execute(
            "SELECT profile_photo FROM students WHERE id=?",
            (session["student_id"],)
        ).fetchone()
        return {"profile_photo": row["profile_photo"] if row else None}
    except Exception:
        return {"profile_photo": None}
    finally:
        if connection:
            connection.close()


@app.after_request
def add_global_navigation(response):
    if (
        "student_id" not in session
        or response.status_code != 200
        or not response.content_type
        or not response.content_type.startswith("text/html")
    ):
        return response

    # Keep the global drawer off focused practice and exam-taking screens.
    # These pages should remain distraction-free; navigation is available
    # again on dashboards, results, and other regular app pages.
    menu_excluded_paths = (
        "/practice",
        "/subject-practice",
        "/pyqs",
        "/mock-tests",
        "/mock-test/",
    )
    current_path = request.path.rstrip("/") or "/"
    if any(
        current_path == excluded.rstrip("/")
        or current_path.startswith(excluded)
        for excluded in menu_excluded_paths
    ):
        return response

    html = response.get_data(as_text=True)

    if "global-menu.css" in html or 'id="cc-global-menu"' in html:
        return response

    asset_version = "20260901"
    assets = (
        f'<link rel="icon" type="image/svg+xml" href="/static/images/civil-career-icon.svg?v=20260924">'
        f'<link rel="apple-touch-icon" href="/static/images/civil-career-icon.svg?v=20260924">'
        f'<link rel="stylesheet" href="/static/css/global-menu.css?v=20260924c">'
        f'<link rel="stylesheet" href="/static/css/mobile.css?v=20260924a">'
        f'<script defer src="/static/js/global-menu.js?v=20260927c"></script>'
        f'<script defer src="/static/js/session-timeout.js?v=20260924b"></script>'
    )
    html = html.replace("</head>", assets + "</head>", 1)

    # Profile photos are shown only inside profile-management controls; do not inject
    # a floating photo/name chip into application pages.

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
        student_columns.add("profile_photo")
    for column_name, column_type in [
        ("profile_photo_data", "BYTEA"),
        ("profile_photo_mime", "TEXT"),
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
        CREATE TABLE IF NOT EXISTS mock_test_attempt_reviews (
            id BIGSERIAL PRIMARY KEY,
            result_id BIGINT NOT NULL UNIQUE,
            student_id INTEGER NOT NULL,
            review_json TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # SSC JE negative marking uses quarter marks. Keep all existing
    # historical scores and widen only the score column to support REAL values.
    try:
        connection.execute("""
            ALTER TABLE mock_test_results
            ALTER COLUMN score TYPE REAL
            USING score::double precision
        """)
        connection.commit()
    except Exception:
        connection.rollback()

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
            "Andhra Pradesh Public Service Commission",
            "Assistant Environmental Engineer – Notification No. 08/2026 (Upcoming)",
            "A.P. Pollution Control Board",
            "State Government / APPSC",
            "Detailed notification pending. Confirm whether Civil, Environmental or allied engineering degrees are accepted before applying.",
            "Civil / Environmental Engineering – verify detailed eligibility",
            "As per detailed notification",
            "As per detailed notification",
            "",
            "",
            "As per detailed notification",
            "2026-10-06",
            "2026-10-27",
            "2026-10-27 23:59",
            "",
            "As per detailed notification",
            "Environmental engineering, pollution control, inspection, compliance and technical duties only as described in the detailed APPSC notification.",
            "As per detailed APPSC notification",
            "Andhra Pradesh",
            "https://portal-psc.ap.gov.in/HomePages/RecruitmentNotifications",
            "https://portal-psc.ap.gov.in/",
            "APPSC",
            "APPSC-08-2026-AEE",
            "2026-09-15",
            "2026-09-27",
            "NEW"
        ),
        (
            "Andhra Pradesh Public Service Commission",
            "Draughtsman Grade-II (Technical Assistant) – Notification No. 15/2026 (Upcoming)",
            "A.P. Forest Subordinate Service",
            "State Government / APPSC",
            "Detailed notification pending. Verify accepted diploma/ITI/engineering qualifications and whether Civil Draughtsman is eligible before applying.",
            "Civil Drafting / Technical Assistant – eligibility pending detailed notification",
            "20 (as stated in the official brief notification; confirm in detailed notification)",
            "As per detailed notification",
            "",
            "",
            "As per detailed notification",
            "2026-10-16",
            "2026-11-05",
            "2026-11-05 23:59",
            "",
            "As per detailed notification",
            "Technical drafting and drawing-related duties as prescribed by the APPSC detailed notification.",
            "As per detailed APPSC notification",
            "Andhra Pradesh",
            "https://portal-psc.ap.gov.in/HomePages/RecruitmentNotifications",
            "https://portal-psc.ap.gov.in/",
            "APPSC",
            "APPSC-15-2026-DRAUGHTSMAN",
            "2026-09-15",
            "2026-09-27",
            "NEW"
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
            qualification='Bachelor''s Degree in Civil Engineering from a recognized University or Institute.',
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

    # Correct UPSC's published ESE 2027 application cutoff to 6:00 PM IST.
    connection.execute(
        """
        UPDATE government_jobs
        SET application_last_datetime='2026-10-06 18:00',
            application_last_date='2026-10-06',
            last_verified='2026-09-27',
            status='OPEN'
        WHERE notification_number='ESE-2027'
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
    # Authenticated students must end their session before viewing the public home page.
    if "student_id" in session:
        session.clear()
        return redirect(url_for("login", logged_out=1))

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
            session["last_activity"] = int(time.time())
            session.permanent = True
            session["student_name"] = student["name"]
            session["student_email"] = student["email"]
            session["student_education"] = student["education"]

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
    unread_notifications_count = connection.execute(
        "SELECT COUNT(*) AS count FROM notification_alerts WHERE user_id=? AND is_read=0",
        (session["student_id"],)
    ).fetchone()["count"]
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
        profile_photo=profile_check["profile_photo"] if profile_check else None,
        job_counts=job_counts,
        unread_notifications_count=unread_notifications_count,
        matching_jobs=matching_jobs,
        overall_progress=overall_progress,
    )

# ==============================
# EXAMS
# ==============================

@app.route("/exams")
def exams():
    """Legacy URL: send students directly to the dashboard; keep all exam sub-pages."""
    if "student_id" not in session:
        return redirect(url_for("login"))
    return redirect(url_for("dashboard"))

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


@app.route("/government-jobs/all")
def government_jobs_all():
    """Show the complete verified Civil Engineering job register, including closed notices."""
    if "student_id" not in session:
        return redirect(url_for("login"))

    filters = {key: request.args.get(key, "").strip() for key in ("search", "qualification", "job_type", "status")}
    connection = get_db_connection()
    rows = connection.execute("""
        SELECT * FROM government_jobs
        WHERE notification_url != '' AND apply_url != '' AND source != ''
          AND vacancies != '' AND qualification != ''
          AND job_role_responsibilities != ''
          AND application_start IS NOT NULL AND application_start != ''
          AND application_last_datetime != ''
          AND (salary != '' OR pay_level != '')
          AND application_fee != ''
        ORDER BY application_last_datetime DESC, organization ASC
    """).fetchall()
    connection.close()

    jobs = []
    counts = {"NEW": 0, "OPEN": 0, "CLOSING SOON": 0, "EXAM DATE ANNOUNCED": 0, "CLOSED": 0}
    for row in rows:
        job = dict(row)
        job["display_status"] = government_job_status(
            job["application_last_date"], job["exam_date"], job["status"]
        )
        job["match_score"] = 0
        if filters["search"] and filters["search"].lower() not in " ".join(
            (job.get("organization", ""), job.get("post_name", ""), job.get("department", ""))
        ).lower():
            continue
        if filters["qualification"] and filters["qualification"].lower() not in job.get("qualification", "").lower():
            continue
        if filters["job_type"] and filters["job_type"].lower() not in job.get("job_type", "").lower():
            continue
        if filters["status"] and filters["status"] != job["display_status"]:
            continue
        jobs.append(job)
        counts[job["display_status"]] = counts.get(job["display_status"], 0) + 1

    return render_template(
        "government_jobs_all.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        jobs=jobs,
        counts=counts,
        filters=filters,
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
        # Core page must contain Civil/technical engineering recruitment only.
        core_civil_terms = (
            "civil", "junior engineer", "assistant engineer", "executive engineer",
            "engineering services", "structural", "geotechnical", "survey",
            "roads", "highway", "irrigation", "water resources", "public works",
            "pwd", "nhai", "cpwd", "bro", "cwc", "ssc je", "rrb je",
            "civil engineering", "construction", "municipal engineer",
            "sub engineer", "overseer", "work inspector", "draftsman"
        )
        civil_haystack = " ".join(str(job.get(k) or "") for k in (
            "organization", "post_name", "department", "qualification", "branch"
        )).lower()
        non_core_exclusions = (
            "civil services", "civil service examination", "ias", "ips", "ifs",
            "group-i", "group-ii", "group 1", "group 2", "ssc cgl", "ssc chsl",
            "ssc mts", "ssc cpo", "ssc gd", "rrb ntpc", "group d", "bank po"
        )
        is_general_service = any(term in civil_haystack for term in non_core_exclusions)
        has_explicit_civil_engineering = any(term in civil_haystack for term in (
            "civil engineering", "junior engineer (civil)", "assistant engineer (civil)",
            "civil works", "civil branch", "civil discipline", "civil -"
        ))
        if is_general_service and not has_explicit_civil_engineering:
            continue
        if not any(term in civil_haystack for term in core_civil_terms):
            continue
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
        civil_job_categories=[
            {"title":"Diploma – Civil Engineering", "posts":"Junior Engineer (Civil), Sub-Engineer, Work Inspector, Overseer, Civil Draughtsman, Surveyor, Technical Assistant and diploma-level site/works posts (only where diploma is accepted)", "recruiters":"APPSC, TGPSC, other State PSCs/Recruitment Boards, State PWD/R&B, Irrigation/Water Resources, Panchayat Raj/Rural Water Supply, Municipalities, PHED, SSC JE and RRB JE (as per notice)", "months":"No single fixed month. State JE/Overseer notices are vacancy-based; check state PSC/board calendars monthly. SSC/RRB publish their own annual or revised calendars."},
            {"title":"B.E. / B.Tech – Civil Engineering", "posts":"Assistant Engineer (Civil), AEE, Engineering Services, Graduate Engineer Trainee, Civil Project/Planning Engineer, Junior Engineer where degree holders qualify, technical officer and works/quality-control posts", "recruiters":"UPSC Engineering Services (ESE), APPSC, TGPSC and other State PSCs, SSC JE, RRB JE/technical posts, CPWD, BRO, NHAI, CWC, state PWD/R&B, Irrigation and eligible central departments", "months":"UPSC/SSC/RRB calendars may be annual but dates change. APPSC/TGPSC and other state AE/JE recruitments depend on vacancies and official notifications. Monitor monthly."},
            {"title":"M.E. / M.Tech – Civil Engineering", "posts":"Specialist Engineer, Structural/Geotechnical/Transportation/Water Resources roles, Scientist/Technical Officer where Civil specializations are named, Assistant Professor/Lecturer and research/project posts", "recruiters":"PSUs and infrastructure authorities, CSIR/DRDO/other research bodies when Civil is specifically listed, IITs/NITs/central universities, APPSC/TGPSC and other state technical education departments", "months":"No common annual month. Faculty, research and specialist openings are institution- or project-based; check official career pages throughout the year."},
            {"title":"PSU & Central Government – Civil", "posts":"Graduate Engineer Trainee, Deputy Manager/Assistant Manager (Civil), Junior Engineer, Assistant Engineer, technical/works officer and project engineering roles", "recruiters":"NHAI, NBCC, RVNL, IRCON, RITES, NHPC, NTPC, Power Grid, SJVN, THDC, BHEL, IOCL, ONGC, CPWD, BRO and other PSUs/departments when Civil is explicitly eligible", "months":"PSU notices are released independently and sometimes use GATE scores. No guaranteed month; monitor each official careers page and GATE-based recruitment notices."},
            {"title":"APPSC / TGPSC / State PSC – Civil", "posts":"AE, AEE, JE, Technical Officer, Assistant Professor and departmental engineering posts based on the recruitment rules", "recruiters":"Andhra Pradesh Public Service Commission (APPSC), Telangana Public Service Commission (TGPSC), and other state PSCs/recruitment boards", "months":"State-wise and vacancy-driven. Track official annual calendars, recruitment notifications, corrigenda and application deadlines."},
            {"title":"Railways & SSC – Civil Technical", "posts":"SSC Junior Engineer (Civil), RRB Junior Engineer (Civil/P-Way/Works), and other railway technical posts only where the exact qualification/branch is accepted", "recruiters":"Staff Selection Commission (SSC), Railway Recruitment Boards (RRBs), Metro rail corporations and relevant official recruiting bodies", "months":"Check SSC/RRB annual calendars and notices throughout the year. Exam dates and vacancies may be revised; use the official notice."},
        ],
        recruitment_month_notes=[
            {"period":"January–March","note":"Check annual exam calendars, UPSC/SSC notices, state budget-year recruitment announcements and PSU career pages; dates vary."},
            {"period":"April–June","note":"Monitor State PSC/JE/AE boards, PSU and infrastructure department vacancies; no common fixed release month."},
            {"period":"July–September","note":"Continue checking state recruitment boards, rail/metro, municipal, irrigation and technical institute notices."},
            {"period":"October–December","note":"Watch revised calendars, year-end/next-year recruitment plans and department-specific vacancies."},
        ],
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

    # In-site cascading syllabus selection. Only course structure transcribed from the
    # identified SBTET AP C-23 Civil curriculum is shown as verified here.
    selected_state = request.args.get("state", "")
    selected_scheme = request.args.get("scheme", "")
    syllabus_result = None
    kind = request.args.get("kind", "")

    ap_c23 = {
        "authority": "SBTET Andhra Pradesh",
        "version": "Curriculum-2023 (C-23)",
        "status": "Course titles/codes shown from the SBTET AP C-23 Civil curriculum scheme. Unit-wise detail is being verified from the subject syllabus pages; this list is not a unit-wise syllabus.",
        "semesters": [
            {"name":"First Year","courses":[
                {"code":"C-101","title":"English","kind":"Theory"},{"code":"C-102","title":"Engineering Mathematics – I","kind":"Theory"},
                {"code":"C-103","title":"Engineering Physics","kind":"Theory"},{"code":"C-104","title":"Engineering Chemistry and Environmental Studies","kind":"Theory"},
                {"code":"C-105","title":"Engineering Mechanics","kind":"Theory"},{"code":"C-106","title":"Surveying-I","kind":"Theory"},
                {"code":"C-107","title":"Engineering Drawing","kind":"Practical"},{"code":"C-108","title":"Surveying-I Practice & Plotting","kind":"Practical"},
                {"code":"C-109","title":"Physics Laboratory","kind":"Practical"},{"code":"C-110","title":"Chemistry Laboratory","kind":"Practical"},
                {"code":"C-111","title":"Computer Fundamentals Practice","kind":"Practical"}]},
            {"name":"Third Semester","courses":[
                {"code":"C-301","title":"Engineering Mathematics – II","kind":"Theory"},{"code":"C-302","title":"Mechanics of Solids & Theory of Structures","kind":"Theory"},
                {"code":"C-303","title":"Hydraulics","kind":"Theory"},{"code":"C-304","title":"Surveying-II","kind":"Theory"},
                {"code":"C-305","title":"Construction Materials","kind":"Theory"},{"code":"C-306","title":"Civil Engineering Drawing-I","kind":"Practical"},
                {"code":"C-307","title":"CAD Practice-I","kind":"Practical"},{"code":"C-308","title":"Surveying-II Practice & Plotting","kind":"Practical"},
                {"code":"C-309","title":"Material Testing Practice","kind":"Practical"},{"code":"C-310","title":"Hydraulics Practice","kind":"Practical"}]},
            {"name":"Fourth Semester","courses":[
                {"code":"C-401","title":"Construction Technology & Valuation","kind":"Theory"},{"code":"C-402","title":"Design and Detailing of R.C. Structures","kind":"Theory"},
                {"code":"C-403","title":"Construction Practice","kind":"Theory"},{"code":"C-404","title":"Transportation Engineering","kind":"Theory"},
                {"code":"C-405","title":"Irrigation Engineering","kind":"Theory"},{"code":"C-406","title":"Civil Engineering Drawing-II","kind":"Practical"},
                {"code":"C-407","title":"Concrete & Soil Testing Practice","kind":"Practical"},{"code":"C-408","title":"Communication Skills","kind":"Practical"},
                {"code":"C-409","title":"Surveying-III Practice","kind":"Practical"},{"code":"C-410","title":"CAD Practice-II","kind":"Practical"}]},
            {"name":"Fifth Semester","courses":[
                {"code":"C-501","title":"Steel Structures","kind":"Theory"},{"code":"C-502","title":"Environmental Engineering","kind":"Theory"},
                {"code":"C-503","title":"Quantity Surveying","kind":"Theory"},{"code":"C-504","title":"Advanced Civil Engineering Technologies","kind":"Theory"},
                {"code":"C-505","title":"Construction Management & Entrepreneurship","kind":"Theory"},{"code":"C-506","title":"Structural Engineering Drawing","kind":"Practical"},
                {"code":"C-507","title":"Field Practices","kind":"Practical"},{"code":"C-508","title":"Life Skills","kind":"Practical"},
                {"code":"C-509","title":"Computer Applications in Civil Engineering","kind":"Practical"},{"code":"C-510","title":"Project Work","kind":"Practical"}]},
            {"name":"Sixth Semester","courses":[{"code":"","title":"Industrial Training (6 months)","kind":"Industrial Training"}]}
        ]
    }

    if kind == "diploma":
        if selected_state == "andhra-pradesh" and selected_scheme == "C-23":
            sem = request.args.get("semester", "")
            selected = next((x for x in ap_c23["semesters"] if x["name"] == sem), None)
            if selected:
                syllabus_result = {"title":f"AP SBTET Civil Engineering — C-23 — {sem}", "status":ap_c23["status"], "semesters":[selected]}
            else:
                syllabus_result = {"title":"AP SBTET Civil Engineering — C-23", "status":ap_c23["status"], "semesters":ap_c23["semesters"]}
        elif selected_state == "telangana":
            syllabus_result = {"title":"Telangana SBTET — Civil Engineering", "status":"The state and scheme selection is recognized, but the exact Civil Engineering scheme and subject-wise document must be verified before publishing subject rows. No AP syllabus is substituted.", "message":"Choose the current scheme and academic year from your Telangana board documents; this in-site syllabus record is pending exact scheme verification."}
        else:
            syllabus_result = {"title":"Diploma syllabus — verification required", "status":"No verified state/scheme-specific curriculum is loaded for this selection.", "message":"Select Andhra Pradesh + C-23 for the verified course structure currently available. Other states/schemes will remain unpublished until their exact official curriculum is verified."}
    elif kind == "btech":
        uni = request.args.get("university","")
        reg = request.args.get("regulation","")
        syllabus_result = {"title":f"{uni} Civil Engineering — {reg}", "status":"Branch-specific official course structure and subject-wise syllabus have not yet been fully verified for this university/regulation. No generic or other-university subject list is shown.", "message":"This selection is captured, but the approved Civil Engineering curriculum must be verified for the exact university, regulation and semester before showing subject or unit data."}
    elif kind == "competitive":
        exam = request.args.get("exam","")
        exam_year = request.args.get("exam_year","")
        syllabus_result = {"title":f"{exam} — {exam_year}", "status":"The exact year/notification-specific syllabus must be verified before displaying its contents.", "message":"No generic competitive syllabus is substituted. This selected exam is awaiting the matching official notification's syllabus text."}

    return render_template(
        "syllabus.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        gate_syllabus=GATE_SYLLABI[syllabus_year],
        gate_syllabi=GATE_SYLLABI,
        syllabus_year=syllabus_year,
        selected_state=selected_state,
        selected_scheme=selected_scheme,
        syllabus_result=syllabus_result
    )



@app.route("/syllabus/<category>")
def syllabus_category(category):
    if "student_id" not in session:
        return redirect(url_for("login"))
    allowed = {"diploma", "btech", "gate", "competitive"}
    if category not in allowed:
        abort(404)

    page_config = {
        "diploma": ("Diploma Syllabus", "State board-wise Diploma Civil Engineering curriculum", "DIPLOMA", "Choose your state, board scheme and semester. Verified curriculum records display here."),
        "btech": ("B.Tech Civil Syllabus", "University and autonomous college curriculum", "B.TECH", "Choose university, regulation and semester. Only the exact verified Civil Engineering curriculum is shown."),
        "gate": ("GATE Civil Engineering", "Year-wise GATE CE syllabus and topic structure", "GATE CE", "Choose the exam year to view syllabus topics for Civil Engineering."),
        "competitive": ("Competitive Exam Syllabus", "Recruitment-notification-specific Civil Engineering syllabus", "COMPETITIVE", "Choose authority, exam and notification year. Syllabi are not merged across different recruitment notices.")
    }
    title, subtitle, label, hero = page_config[category]
    result = None

    if request.args:
        if category == "diploma":
            state = request.args.get("state", "")
            scheme = request.args.get("scheme", "")
            semester = request.args.get("semester", "")
            if state == "andhra-pradesh" and scheme == "C-23":
                records = [
                    {"name":"First Year","courses":[{"code":"C-101","title":"English","kind":"Theory"},{"code":"C-102","title":"Engineering Mathematics – I","kind":"Theory"},{"code":"C-103","title":"Engineering Physics","kind":"Theory"},{"code":"C-104","title":"Engineering Chemistry and Environmental Studies","kind":"Theory"},{"code":"C-105","title":"Engineering Mechanics","kind":"Theory"},{"code":"C-106","title":"Surveying-I","kind":"Theory"},{"code":"C-107","title":"Engineering Drawing","kind":"Practical"},{"code":"C-108","title":"Surveying-I Practice & Plotting","kind":"Practical"},{"code":"C-109","title":"Physics Laboratory","kind":"Practical"},{"code":"C-110","title":"Chemistry Laboratory","kind":"Practical"},{"code":"C-111","title":"Computer Fundamentals Practice","kind":"Practical"}]},
                    {"name":"Third Semester","courses":[{"code":"C-301","title":"Engineering Mathematics – II","kind":"Theory"},{"code":"C-302","title":"Mechanics of Solids & Theory of Structures","kind":"Theory"},{"code":"C-303","title":"Hydraulics","kind":"Theory"},{"code":"C-304","title":"Surveying-II","kind":"Theory"},{"code":"C-305","title":"Construction Materials","kind":"Theory"},{"code":"C-306","title":"Civil Engineering Drawing-I","kind":"Practical"},{"code":"C-307","title":"CAD Practice-I","kind":"Practical"},{"code":"C-308","title":"Surveying-II Practice & Plotting","kind":"Practical"},{"code":"C-309","title":"Material Testing Practice","kind":"Practical"},{"code":"C-310","title":"Hydraulics Practice","kind":"Practical"}]},
                    {"name":"Fourth Semester","courses":[{"code":"C-401","title":"Construction Technology & Valuation","kind":"Theory"},{"code":"C-402","title":"Design and Detailing of R.C. Structures","kind":"Theory"},{"code":"C-403","title":"Construction Practice","kind":"Theory"},{"code":"C-404","title":"Transportation Engineering","kind":"Theory"},{"code":"C-405","title":"Irrigation Engineering","kind":"Theory"},{"code":"C-406","title":"Civil Engineering Drawing-II","kind":"Practical"},{"code":"C-407","title":"Concrete & Soil Testing Practice","kind":"Practical"},{"code":"C-408","title":"Communication Skills","kind":"Practical"},{"code":"C-409","title":"Surveying-III Practice","kind":"Practical"},{"code":"C-410","title":"CAD Practice-II","kind":"Practical"}]},
                    {"name":"Fifth Semester","courses":[{"code":"C-501","title":"Steel Structures","kind":"Theory"},{"code":"C-502","title":"Environmental Engineering","kind":"Theory"},{"code":"C-503","title":"Quantity Surveying","kind":"Theory"},{"code":"C-504","title":"Advanced Civil Engineering Technologies","kind":"Theory"},{"code":"C-505","title":"Construction Management & Entrepreneurship","kind":"Theory"},{"code":"C-506","title":"Structural Engineering Drawing","kind":"Practical"},{"code":"C-507","title":"Field Practices","kind":"Practical"},{"code":"C-508","title":"Life Skills","kind":"Practical"},{"code":"C-509","title":"Computer Applications in Civil Engineering","kind":"Practical"},{"code":"C-510","title":"Project Work","kind":"Practical"}]},
                    {"name":"Sixth Semester","courses":[{"code":"","title":"Industrial Training (6 months)","kind":"Industrial Training"}]}
                ]
                chosen = [x for x in records if not semester or x["name"] == semester]
                result = {"title":f"AP SBTET Civil Engineering — C-23 — {semester or 'Course Structure'}","status":"Course codes and titles transcribed from the AP SBTET Curriculum-2023 scheme. This is the scheme/course structure, not the detailed unit-wise syllabus; unit detail must be verified from the official subject pages before being labeled complete.","semesters":chosen,"download_available":bool(chosen)}
            else:
                result = {"title":"Syllabus not yet verified for this selection","status":"No verified record loaded for this exact state and scheme.","message":"This selected board/scheme has not been fully transcribed and checked yet. To avoid fabricated syllabus data, Civil Career will not substitute another state's or scheme's syllabus."}
        elif category == "btech":
            uni=request.args.get("university","").strip()
            reg=request.args.get("regulation","").strip()
            sem=request.args.get("semester","").strip()
            college_name=request.args.get("college_name","").strip()
            university_label=f"{uni} — {college_name}" if uni=="Autonomous college" and college_name else uni
            curriculum_data={}
            syllabus_data_path=os.path.join(app.root_path,"data","btech_civil_syllabus.json")
            try:
                with open(syllabus_data_path,"r",encoding="utf-8") as syllabus_file:
                    curriculum_data=json.load(syllabus_file)
            except (OSError,json.JSONDecodeError):
                curriculum_data={}
            curricula=curriculum_data.get("curricula",[])
            selected_record=next((record for record in curricula
                if record.get("university")==uni
                and record.get("regulation")==reg
                and (uni!="Autonomous college" or record.get("college_name","").casefold()==college_name.casefold())),None)
            if uni=="Autonomous college" and not college_name:
                result={"title":"Autonomous college name required","status":"Enter the exact autonomous college name.","message":"Each autonomous college may publish a separate curriculum. Please enter its official name to look for the matching curriculum record.","semesters":[],"sections":[],"download_available":False}
            elif selected_record:
                all_semesters=selected_record.get("semesters",[])
                selected_semesters=[item for item in all_semesters if not sem or item.get("name")==sem]
                courses_count=sum(len(item.get("courses",[])) for item in selected_semesters)
                has_topic_data=any(course.get("topics") for item in selected_semesters for course in item.get("courses",[]))
                status=f"Official curriculum course structure loaded ({len(selected_semesters)} semester(s), {courses_count} course records)."
                if has_topic_data:
                    status+=" Subject-wise unit topics are available for the courses whose official unit text has been transcribed."
                result={"title":f"{university_label} Civil Engineering — {reg} — {sem or 'All available semesters'}","status":status,"source_url":selected_record.get("source_url"),"source_label":"Official curriculum source","selection":f"{university_label} · {reg} · {sem or 'All available semesters'}","semesters":selected_semesters,"sections":[],"download_available":False,"message":"Click a subject to open its unit-wise topics. Where the official source currently provides only the course title/structure, the subject detail panel explicitly identifies that unit topics are not yet transcribed."}
            elif uni and reg:
                result={"title":f"{university_label} Civil Engineering — {reg} — {sem or 'All semesters'}","status":"This exact curriculum record has not yet been transcribed into Civil Career.","message":"No course list or topic outline has been loaded for this exact university/college and regulation yet. Civil Career will not fill it with another university's syllabus. The official source archive is available below; the matching official syllabus must be transcribed before topics can be represented as that curriculum.","selection":f"{university_label} · {reg} · {sem or 'All semesters'}","semesters":[],"sections":[],"download_available":False}
        elif category == "gate":
            year=request.args.get("year","2027")
            gate_data=GATE_SYLLABI.get(year,{})
            sections=[]
            # Syllabus records may be a list of subject dictionaries or a keyed mapping.
            if isinstance(gate_data,(list,tuple)):
                for entry in gate_data:
                    if isinstance(entry,dict):
                        subject=entry.get("subject") or entry.get("title") or entry.get("name") or "Syllabus topics"
                        topics=entry.get("topics") or entry.get("items") or entry.get("syllabus") or []
                        if isinstance(topics,dict):
                            items=[f"{k}: {v}" for k,v in topics.items()]
                        elif isinstance(topics,(list,tuple)):
                            items=[str(x) for x in topics]
                        elif isinstance(topics,str):
                            items=[topics]
                        else:
                            items=[]
                        if items:
                            sections.append({"title":str(subject),"items":items})
                    elif isinstance(entry,str):
                        sections.append({"title":"Syllabus","items":[entry]})
            elif isinstance(gate_data,dict):
                for key,value in gate_data.items():
                    if isinstance(value,(list,tuple)):
                        sections.append({"title":str(key).replace("_"," ").title(),"items":[str(x) for x in value]})
                    elif isinstance(value,dict):
                        nested_title=value.get("subject") or value.get("title") or str(key).replace("_"," ").title()
                        nested=value.get("topics") or value.get("items") or value.get("syllabus")
                        if isinstance(nested,(list,tuple)):
                            items=[str(x) for x in nested]
                        elif isinstance(nested,dict):
                            items=[f"{k}: {v}" for k,v in nested.items()]
                        else:
                            items=[f"{k}: {v}" for k,v in value.items() if k not in ("subject","title","name")]
                        if items:
                            sections.append({"title":str(nested_title),"items":items})
                    elif isinstance(value,str):
                        sections.append({"title":str(key).replace("_"," ").title(),"items":[value]})
            result={"title":f"GATE Civil Engineering — {year}","status":f"Syllabus topics loaded from Civil Career's configured {year} record. Cross-check the official GATE {year} notification before exam use.","sections":sections,"message":"No formatted syllabus topics were found in the configured year record."}
        elif category == "competitive":
            authority=request.args.get("authority","").strip()
            exam=request.args.get("exam","").strip()
            notification=request.args.get("notification","").strip()
            official_sources={
                "SSC":"https://ssc.gov.in/",
                "UPSC":"https://www.upsc.gov.in/",
                "Andhra Pradesh":"https://psc.ap.gov.in/",
                "Telangana":"https://www.tgpsc.gov.in/",
            }
            valid_selection=bool(authority and exam and notification and notification.isdigit() and len(notification)==4)
            if valid_selection:
                result={
                    "title":f"{exam} | {authority} | Notification {notification}",
                    "status":"Exact-notification record status: pending official document verification. No syllabus topics have been published for this selection yet.",
                    "message":f"Civil Career has not yet verified and transcribed the official {notification} recruitment notification for {exam} ({authority}). Open the recruiting authority's official website and locate the matching notification, corrigenda and syllabus annexure. Topics will appear here only after the exact notice is checked; no other year's or exam's syllabus is substituted.",
                    "source_url":official_sources.get(authority),
                    "source_label":f"Visit {authority} official website",
                    "selection":f"{authority} · {exam} · {notification}",
                    "download_available":False,
                    "sections":[]
                }
            else:
                result={
                    "title":"Complete the recruitment selection",
                    "status":"Select an authority, examination and four-digit notification year to check its record.",
                    "message":"The syllabus is tied to a specific recruitment notice. Choose all three filters above. Civil Career will not merge syllabus topics across authorities, exams or notification years.",
                    "download_available":False,
                    "sections":[]
                }

    return render_template("syllabus_category.html",category=category,page_title=title,page_subtitle=subtitle,category_label=label,hero_title=title,hero_text=hero,syllabus_result=result,student_name=session.get("student_name","Student"),student_education=session.get("student_education",""))


@app.route("/syllabus/<category>/download.pdf")
def download_syllabus_category_pdf(category):
    if "student_id" not in session:
        return redirect(url_for("login"))
    if category not in {"diploma","btech","gate","competitive"}:
        abort(404)
    # Never generate a placeholder PDF that could be mistaken for an official syllabus.
    if category == "btech":
        if not (request.args.get("university") == "JNTUK" and request.args.get("regulation") == "R23" and request.args.get("semester") == "IV Year - I Semester"):
            abort(404, description="The exact university/regulation syllabus is not yet verified and transcribed. A placeholder PDF is disabled.")
    if category == "competitive":
        abort(404, description="The exact recruitment-notification syllabus is not yet verified. A placeholder PDF is disabled.")
    # Reuse the selected in-site result by reconstructing the exact selection.
    args=request.args
    title=f"{category.title()} Civil Engineering Syllabus"
    story=[]
    styles=getSampleStyleSheet()
    story.append(Paragraph("CIVIL CAREER",styles["Title"]))
    story.append(Paragraph(escape(title),styles["Heading1"]))
    story.append(Paragraph("Selection: "+escape(" | ".join(f"{k}: {v}" for k,v in args.items())),styles["Normal"]))
    story.append(Spacer(1,12))
    story.append(Paragraph("This PDF is generated from the syllabus content available for the selected category in Civil Career. Where the exact official document has not been verified and transcribed, the PDF states that limitation instead of inventing syllabus details.",styles["BodyText"]))
    if category=="diploma" and args.get("state")=="andhra-pradesh" and args.get("scheme")=="C-23":
        subjects={
          "First Year":[("C-101","English"),("C-102","Engineering Mathematics – I"),("C-103","Engineering Physics"),("C-104","Engineering Chemistry and Environmental Studies"),("C-105","Engineering Mechanics"),("C-106","Surveying-I"),("C-107","Engineering Drawing"),("C-108","Surveying-I Practice & Plotting"),("C-109","Physics Laboratory"),("C-110","Chemistry Laboratory"),("C-111","Computer Fundamentals Practice")],
          "Third Semester":[("C-301","Engineering Mathematics – II"),("C-302","Mechanics of Solids & Theory of Structures"),("C-303","Hydraulics"),("C-304","Surveying-II"),("C-305","Construction Materials"),("C-306","Civil Engineering Drawing-I"),("C-307","CAD Practice-I"),("C-308","Surveying-II Practice & Plotting"),("C-309","Material Testing Practice"),("C-310","Hydraulics Practice")],
          "Fourth Semester":[("C-401","Construction Technology & Valuation"),("C-402","Design and Detailing of R.C. Structures"),("C-403","Construction Practice"),("C-404","Transportation Engineering"),("C-405","Irrigation Engineering"),("C-406","Civil Engineering Drawing-II"),("C-407","Concrete & Soil Testing Practice"),("C-408","Communication Skills"),("C-409","Surveying-III Practice"),("C-410","CAD Practice-II")],
          "Fifth Semester":[("C-501","Steel Structures"),("C-502","Environmental Engineering"),("C-503","Quantity Surveying"),("C-504","Advanced Civil Engineering Technologies"),("C-505","Construction Management & Entrepreneurship"),("C-506","Structural Engineering Drawing"),("C-507","Field Practices"),("C-508","Life Skills"),("C-509","Computer Applications in Civil Engineering"),("C-510","Project Work")],
          "Sixth Semester":[("","Industrial Training (6 months)")]
        }
        selected=args.get("semester","")
        for sem,rows in subjects.items():
            if not selected or selected==sem:
                story.append(Paragraph(escape(sem),styles["Heading2"]))
                table=Table([["Code","Subject / Course"]]+[[code,name] for code,name in rows],colWidths=[35*mm,130*mm],repeatRows=1)
                table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#12366b")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.grey),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),7)]))
                story.append(table);story.append(Spacer(1,10))
    elif category=="btech" and args.get("university")=="JNTUK" and args.get("regulation")=="R23" and args.get("semester")=="IV Year - I Semester":
        story.append(Paragraph("JNTUK B.Tech R23 — Civil Engineering — IV Year I Semester",styles["Heading2"]))
        story.append(Paragraph("Verified course structure from the JNTUK B.Tech R23 Engineering Curriculum 2023. The common course-structure table lists course categories and credits, not the Civil-specific course titles or unit-wise content for these slots.",styles["BodyText"]))
        rows=[["Course / component","L-T-P-C / credits"],["Professional Core 1","3-0-0-3"],["Professional Core 2","3-0-0-3"],["Management Course-II","2-0-0-2"],["Professional Elective-IV","3-0-0-3"],["Professional Elective-V","3-0-0-3"],["Open Elective-IV","3-0-0-3"],["Professional Core Lab 1","0-0-2-1"],["Professional Core Lab 2","0-0-2-1"],["Skill Enhancement Course","0-1-2-2"],["Audit Course: Constitution of India","2-0-0 (non-credit)"],["Internship Evaluation of Industry Internship","2 credits"],["Semester total","19 lecture + 1 tutorial + 6 practical hours; 23 credits"]]
        table=Table(rows,colWidths=[105*mm,60*mm],repeatRows=1)
        table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#12366b")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.4,colors.grey),("VALIGN",(0,0),(-1,-1),"TOP"),("PADDING",(0,0),(-1,-1),7)]))
        story.append(table)
        story.append(Spacer(1,12))
        story.append(Paragraph("Source: JNTUK B.Tech R23 Engineering Curriculum 2023, IV Year-I semester course-structure section (page 27 in the PDF edition reviewed).",styles["Italic"]))
    else:
        story.append(Paragraph("Verified syllabus content for this exact selection has not yet been added. This PDF is a status sheet, not a substitute syllabus.",styles["Heading2"]))
    output=BytesIO()
    doc=SimpleDocTemplate(
        output, pagesize=A4, rightMargin=18*mm, leftMargin=18*mm,
        topMargin=25*mm, bottomMargin=20*mm, title=title, author="Civil Career"
    )
    doc.build(
        story,
        onFirstPage=lambda canvas, document: draw_civilcareer_pdf_chrome(
            canvas, document, header_right=title, footer_label=title
        ),
        onLaterPages=lambda canvas, document: draw_civilcareer_pdf_chrome(
            canvas, document, header_right=title, footer_label=title
        )
    )
    output.seek(0)
    return send_file(output,as_attachment=True,download_name=f"civilcareer_{category}_syllabus.pdf",mimetype="application/pdf")


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
        draw_civilcareer_pdf_chrome(
            canvas, document,
            header_right="GATE " + year + " | Civil Engineering",
            footer_label="GATE " + year + " Civil Engineering Syllabus"
        )

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
            "Website: " + escape(PDF_WEBSITE_URL) +
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

@app.route("/official-sources")
def official_sources():
    """In-site dashboard for official syllabus and recruitment-source monitoring."""
    if "student_id" not in session:
        return redirect(url_for("login"))
    registry_path = os.path.join(app.root_path, "data", "official_sources.json")
    state_path = os.path.join(app.root_path, "data", "official_source_state.json")
    try:
        with open(registry_path, "r", encoding="utf-8") as source_file:
            registry = json.load(source_file)
    except (OSError, json.JSONDecodeError):
        registry = {"sources": []}
    try:
        with open(state_path, "r", encoding="utf-8") as state_file:
            state = json.load(state_file)
    except (OSError, json.JSONDecodeError):
        state = {"sources": {}, "last_run_at": None}
    cards = []
    for source in registry.get("sources", []):
        if not source.get("enabled", True):
            continue
        status = state.get("sources", {}).get(source.get("id", ""), {})
        cards.append({
            "title": source.get("title", "Official source"),
            "authority": source.get("authority", ""),
            "category": source.get("category", ""),
            "url": source.get("url", ""),
            "status": status.get("status", "waiting_for_first_check"),
            "checked_at": status.get("checked_at"),
            "review_status": status.get("review_status", "not_yet_archived"),
            "last_error": status.get("last_error")
        })
    return render_template(
        "official_sources.html", sources=cards,
        last_run_at=state.get("last_run_at"),
        student_name=session.get("student_name", "Student"),
        student_education=session.get("student_education", "")
    )


@app.route("/materials")
def materials():
    if "student_id" not in session:
        return redirect(url_for("login"))
    return render_template(
        "materials.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )


@app.route("/materials/diploma-c23")
def diploma_c23_materials():
    """C-23 subject catalogue with explicit pending status for unverified units."""
    if "student_id" not in session:
        return redirect(url_for("login"))

    semester = request.args.get("semester", "").strip()
    subject_code = request.args.get("subject", "").strip().upper()
    valid_semesters = {"FY", "3", "4", "5", "6"}
    if semester not in valid_semesters:
        semester = ""

    catalogue_path = os.path.join(app.root_path, "data", "ap_sbtet_c23_civil_subjects.json")
    catalogue = {"courses": []}
    try:
        with open(catalogue_path, "r", encoding="utf-8") as catalogue_file:
            catalogue = json.load(catalogue_file)
    except (OSError, json.JSONDecodeError) as exc:
        app.logger.error("Could not load C-23 subject catalogue: %s", exc)

    term_key = "First Year" if semester == "FY" else semester
    semester_courses = [
        course for course in catalogue.get("courses", [])
        if course.get("term") == term_key
    ] if semester else []

    selected_subject = next(
        (course for course in semester_courses if course.get("code", "").upper() == subject_code),
        None
    )
    if not selected_subject:
        subject_code = ""

    official_curriculum_url = catalogue.get(
        "source_url",
        "https://polytechnic.aec.edu.in/docs/syllabus/C_23/CE.pdf"
    )
    official_board_url = "https://sbtet.ap.gov.in/"

    return render_template(
        "materials_diploma_c23.html",
        student_name=session.get("student_name", "Student"),
        student_education=session.get("student_education", ""),
        semester=semester,
        subject_code=subject_code,
        semester_courses=semester_courses,
        selected_subject=selected_subject,
        official_curriculum_url=official_curriculum_url,
        official_board_url=official_board_url
    )


@app.route("/materials/<category>")
def materials_category(category):
    """Separate category pages; syllabus details are linked to their issuing authority."""
    if "student_id" not in session:
        return redirect(url_for("login"))

    pages = {
        "college": {
            "title": "College Materials",
            "subtitle": "Diploma / B.Tech college study resources, organized by official curriculum context.",
            "contexts": [
                {"icon":"🎓","tag":"DIPLOMA","title":"Diploma — State Board","description":"Select your state SBTET, scheme, semester and Civil Engineering subject from the official syllabus directory.","href":url_for("syllabus")+"#diploma-official","action":"Select board and syllabus"},
                {"icon":"🏛️","tag":"B.TECH","title":"B.Tech — University","description":"Choose JNTU/university, regulation, semester and subject. Use autonomous college curriculum where applicable.","href":url_for("syllabus")+"#btech-official","action":"Select university"},
                {"icon":"🏫","tag":"AUTONOMOUS","title":"Autonomous college","description":"Use the approved syllabus published for your college and admission batch; college-specific verification is required.","href":url_for("syllabus")+"#btech-official","action":"Find official curriculum"}
            ]
        },
        "formulas": {
            "title":"Formula Sheets",
            "subtitle":"Formula resources must match the selected syllabus subject and topic.",
            "contexts":[
                {"icon":"📐","tag":"COLLEGE","title":"Diploma / B.Tech formulas","description":"Select the relevant board/university regulation and subject before using a formula sheet.","href":url_for("syllabus")+"#official-syllabus","action":"Choose syllabus"},
                {"icon":"🏆","tag":"GATE CE","title":"GATE Civil formulas","description":"Use the official GATE CE syllabus for the selected year to determine included topics.","href":url_for("syllabus")+"#gate-official","action":"Check GATE syllabus"},
                {"icon":"📄","tag":"JE / AE / ESE","title":"Recruitment-specific formulas","description":"Select the exact recruitment notice and year; scope can differ by authority and exam.","href":url_for("syllabus")+"#recruitment-official","action":"Check notification"}
            ]
        },
        "competitive": {
            "title":"Competitive Materials",
            "subtitle":"Exam-specific resources linked to the current official syllabus or recruitment notification.",
            "contexts":[
                {"icon":"🏆","tag":"GATE","title":"GATE CE","description":"Select exam year and official CE syllabus before organizing subject notes.","href":url_for("syllabus")+"#gate-official","action":"Open official GATE source"},
                {"icon":"📄","tag":"SSC","title":"SSC JE","description":"Use the current SSC notification's paper pattern and Civil Engineering syllabus.","href":url_for("syllabus")+"#recruitment-official","action":"Open SSC syllabus source"},
                {"icon":"🏛️","tag":"ESE / JE / AE","title":"UPSC / State / Department","description":"Requires exact recruiting authority and notification number/year to verify syllabus scope.","href":url_for("syllabus")+"#recruitment-official","action":"Choose recruitment notice"}
            ]
        },
        "notes": {
            "title":"Subject Notes",
            "subtitle":"Brief human-readable learning notes, grouped only after the official syllabus context is selected.",
            "contexts":[
                {"icon":"🎓","tag":"COLLEGE","title":"College subject notes","description":"Select board/university, regulation, semester and subject. Unverified curriculum mapping is not supplied.","href":url_for("syllabus")+"#official-syllabus","action":"Select syllabus"},
                {"icon":"🏆","tag":"COMPETITIVE","title":"Exam topic notes","description":"Select the official exam year or recruitment notification and match notes to its topics.","href":url_for("syllabus")+"#recruitment-official","action":"Select exam source"}
            ]
        }
    }
    page = pages.get(category)
    if not page:
        abort(404)
    return render_template(
        "materials_section.html",
        page_title=page["title"],
        page_subtitle=page["subtitle"],
        contexts=page["contexts"],
        student_name=session.get("student_name","Student"),
        student_education=session.get("student_education","")
    )

# ==============================
# NOTIFICATIONS
# ==============================

@app.route("/api/notifications/unread-count")
def api_notification_unread_count():
    """Return the current student's unread notification count and latest alert for live bell updates."""
    if "student_id" not in session:
        return jsonify({"authenticated": False, "count": 0}), 401

    connection = get_db_connection()
    try:
        count_row = connection.execute(
            "SELECT COUNT(*) AS count FROM notification_alerts WHERE user_id=? AND is_read=0",
            (session["student_id"],)
        ).fetchone()
        latest = connection.execute(
            """
            SELECT id, category, title, message, link_url, created_at
            FROM notification_alerts
            WHERE user_id=? AND is_read=0
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (session["student_id"],)
        ).fetchone()
        latest_alert = dict(latest) if latest else None
        return jsonify({
            "authenticated": True,
            "count": int(count_row["count"] or 0),
            "latest": latest_alert
        })
    finally:
        connection.close()


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

    alert_dicts = []
    unread_count = connection.execute(
        "SELECT COUNT(*) AS count FROM notification_alerts WHERE user_id=? AND is_read=0",
        (session["student_id"],)
    ).fetchone()["count"]
    connection.close()

    # Convert database UTC timestamps to readable Indian Standard Time.
    for alert in alerts:
        alert_dict = dict(alert)
        raw_created = alert_dict.get("created_at")
        try:
            parsed_created = datetime.fromisoformat(str(raw_created).replace("Z", "+00:00"))
            if parsed_created.tzinfo is None:
                parsed_created = parsed_created.replace(tzinfo=ZoneInfo('UTC'))
            alert_dict["created_at_display"] = parsed_created.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")
        except (ValueError, TypeError):
            alert_dict["created_at_display"] = "Date unavailable"
        alert_dicts.append(alert_dict)

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
        notification_alerts=alert_dicts,
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

    connection = get_db_connection()
    try:
        stats = connection.execute(
            """
            SELECT COUNT(*) AS tests_completed,
                   COALESCE(SUM(total_questions - unanswered), 0) AS questions_attempted,
                   COALESCE(SUM(correct), 0) AS correct_answers,
                   COALESCE(SUM(wrong), 0) AS wrong_answers,
                   COALESCE(MAX(percentage), 0) AS best_score
            FROM mock_test_results WHERE student_id=?
            """, (session["student_id"],)
        ).fetchone()
        stats = dict(stats or {})
    finally:
        connection.close()

    attempted = int(stats.get("questions_attempted") or 0)
    correct = int(stats.get("correct_answers") or 0)
    wrong = int(stats.get("wrong_answers") or 0)
    accuracy = round((correct / (correct + wrong)) * 100) if correct + wrong else 0
    return render_template(
        "practice.html", student_name=session["student_name"],
        student_education=session["student_education"],
        practice_stats={
            "questions_attempted": attempted, "accuracy": accuracy,
            "tests_completed": int(stats.get("tests_completed") or 0),
            "best_score": round(float(stats.get("best_score") or 0))
        }
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

    connection = get_db_connection()
    student = connection.execute(
        "SELECT profile_photo, profile_photo_data, profile_photo_mime "
        "FROM students WHERE id=?",
        (session["student_id"],)
    ).fetchone()
    connection.close()

    # Prefer the database copy so profile pictures survive Railway redeploys.
    if student and student["profile_photo"] == safe_name and student["profile_photo_data"]:
        return send_file(
            BytesIO(bytes(student["profile_photo_data"])),
            mimetype=student["profile_photo_mime"] or "image/jpeg",
            download_name=safe_name,
        )

    # Backward-compatible fallback for older filesystem uploads.
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
                filename = secure_filename(
                    "student-" + str(session["student_id"]) + "-" +
                    uuid.uuid4().hex + "." + extension
                )
                photo_bytes = photo.read()
                mime_type = photo.mimetype or (
                    "image/png" if extension == "png"
                    else "image/webp" if extension == "webp"
                    else "image/jpeg"
                )

                # Store the image in PostgreSQL so it is not lost when
                # Railway replaces the container during a deployment.
                connection.execute(
                    "UPDATE students SET profile_photo=?, profile_photo_data=?, "
                    "profile_photo_mime=? WHERE id=?",
                    (filename, photo_bytes, mime_type, session["student_id"])
                )
                connection.commit()

                # Keep a local copy as a compatibility fallback.
                try:
                    os.makedirs(app.config["PROFILE_UPLOAD_FOLDER"], exist_ok=True)
                    with open(
                        os.path.join(app.config["PROFILE_UPLOAD_FOLDER"], filename),
                        "wb"
                    ) as image_file:
                        image_file.write(photo_bytes)
                except Exception as exc:
                    print(
                        f"[PROFILE PHOTO FILE FALLBACK] {type(exc).__name__}: {exc}",
                        flush=True,
                    )

                profile_message = "Profile photo updated successfully."

    student = connection.execute(
        """SELECT id,user_id,name,email,education,profile_photo,
                  profile_photo_data,profile_photo_mime,
                  mobile_country_code,mobile_number,
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
# STUDENT MOCK TEST HISTORY
# ==========================================

@app.route("/mock-test-history")
def mock_test_history_list():
    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    results = connection.execute(
        """
        SELECT id, exam_name, total_questions, correct, wrong,
               unanswered, score, percentage, created_at
        FROM mock_test_results
        WHERE student_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (session["student_id"],)
    ).fetchall()
    connection.close()

    rows = ""
    for item in results:
        safe_exam_name = escape(str(item["exam_name"] or "Mock Test"))
        safe_created_at = escape(format_datetime_ist(item["created_at"], include_seconds=True))
        rows += f"""
        <tr>
          <td>{safe_exam_name}</td>
          <td>{safe_created_at}</td>
          <td>{int(item['total_questions'] or 0)}</td>
          <td>{int(item['correct'] or 0)}</td>
          <td>{int(item['wrong'] or 0)}</td>
          <td><strong>{escape(str(item['score'] or 0))}</strong></td>
          <td>{float(item['percentage'] or 0):.1f}%</td>
          <td><div class="history-menu-wrap"><button type="button" class="history-menu-btn" aria-label="Attempt actions" aria-expanded="false" onclick="toggleAttemptMenu(this)">⋮</button><div class="history-menu"><a href="/mock-test-history/{int(item['id'])}">View</a><a href="/mock-test-history/{int(item['id'])}/download">Download PDF</a><form method="post" action="/mock-test-history/{int(item['id'])}/delete" onsubmit="return confirm('Delete this saved mock test attempt? This cannot be undone.');"><button type="submit" class="delete-action">Delete</button></form></div></div></td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="8" class="empty">No mock-test attempts yet. Start a test to see your history here.</td></tr>'

    page = """
    <!doctype html><html lang="en"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Mock Test History | Civil Career</title>
    <style>
    *{box-sizing:border-box}body{margin:0;background:#f1f5f9;font-family:Inter,"Segoe UI",Arial,sans-serif;color:#0f172a}
    .wrap{max-width:1200px;margin:0 auto;padding:32px 22px}.top{display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:24px}
    .back{color:#2563eb;text-decoration:none;font-weight:700}.title{font-size:clamp(25px,4vw,36px);margin:18px 0 6px}.sub{color:#64748b;margin:0}
    
    
    .panel{background:#fff;border:1px solid #e2e8f0;border-radius:18px;overflow:hidden;box-shadow:0 12px 30px #0f172a0a}
    .panelhead{padding:22px 24px;border-bottom:1px solid #e2e8f0;display:flex;justify-content:space-between;gap:12px;align-items:center;flex-wrap:wrap}
    .pill{background:#eff6ff;color:#1d4ed8;padding:8px 13px;border-radius:99px;font-size:13px;font-weight:700}
    .tablewrap{overflow-x:auto}table{width:100%;border-collapse:collapse;min-width:850px}th,td{padding:16px 18px;text-align:left;border-bottom:1px solid #f1f5f9;font-size:14px}th{background:#f8fafc;color:#475569;font-size:12px;text-transform:uppercase;letter-spacing:.04em}tbody tr:hover{background:#f8fafc}.view{color:#2563eb;text-decoration:none;font-weight:700}.empty{text-align:center;padding:42px;color:#64748b}
    .actions{display:flex;gap:10px}.history-menu-wrap{position:relative;display:inline-block}.history-menu-btn{width:38px;height:38px;border:1px solid #cbd5e1;border-radius:10px;background:#fff;color:#0f172a;font-size:25px;line-height:1;cursor:pointer}.history-menu-btn:hover,.history-menu-btn[aria-expanded="true"]{background:#eff6ff;border-color:#93c5fd}.history-menu{display:none;position:absolute;right:0;top:43px;min-width:155px;background:#fff;border:1px solid #e2e8f0;border-radius:12px;box-shadow:0 12px 30px #0f172a24;padding:6px;z-index:30}.history-menu.open{display:block}.history-menu a,.history-menu form button{display:block;width:100%;padding:10px 12px;border:0;background:transparent;text-align:left;text-decoration:none;color:#1e293b;font:600 13px Arial;border-radius:8px;cursor:pointer}.history-menu a:hover,.history-menu form button:hover{background:#f1f5f9}.history-menu .delete-action{color:#b91c1c}.btn{display:inline-block;text-decoration:none;padding:11px 16px;border-radius:10px;background:#2563eb;color:white;font-weight:700}.btn.secondary{background:#e2e8f0;color:#334155}.btn.danger-all{border:0;background:#dc2626;color:#fff;cursor:pointer;font-size:14px}.btn.danger-all:hover{background:#b91c1c}
    @media(max-width:600px){.wrap{padding:20px 12px}.panelhead{padding:18px}}
    </style></head><body><main class="wrap">
    <div class="top"><a class="back" href="/mock-tests">← Back to Mock Tests</a><form method="post" action="/mock-test-history/delete-all" onsubmit="return confirm('Delete ALL your saved mock test attempts and answer reviews? This cannot be undone.');"><button type="submit" class="btn danger-all">Delete All</button></form>
    </div>
    <h1 class="title">Mock Test History</h1><p class="sub">Review your previous attempts, scores, and detailed performance.</p>
    <section class="panel" style="margin-top:24px"><div class="panelhead"><strong>📚 Your Attempts</strong><span class="pill">__COUNT__ attempt(s)</span></div>
    <div class="tablewrap"><table><thead><tr><th>Exam</th><th>Date &amp; Time</th><th>Questions</th><th>Correct</th><th>Wrong</th><th>Score</th><th>Percentage</th><th>Review</th></tr></thead><tbody>__ROWS__</tbody></table></div></section>
    <div class="actions" style="margin-top:22px"><a class="btn" href="/mock-tests">Start a Mock Test</a><a class="btn secondary" href="/practice">Back to Practice</a></div></main><script>function toggleAttemptMenu(btn){const menu=btn.nextElementSibling;document.querySelectorAll(".history-menu.open").forEach(m=>{if(m!==menu){m.classList.remove("open");m.previousElementSibling.setAttribute("aria-expanded","false")}});menu.classList.toggle("open");btn.setAttribute("aria-expanded",String(menu.classList.contains("open")));}document.addEventListener("click",e=>{if(!e.target.closest(".history-menu-wrap"))document.querySelectorAll(".history-menu.open").forEach(m=>{m.classList.remove("open");m.previousElementSibling.setAttribute("aria-expanded","false")})});</script></main></body></html>
    """
    page = page.replace("__COUNT__", str(len(results))).replace("__ROWS__", rows)
    return page


@app.route("/mock-test-history/delete-all", methods=["POST"])
def delete_all_mock_test_history():
    if "student_id" not in session:
        return redirect(url_for("login"))
    connection = get_db_connection()
    try:
        student_id = session["student_id"]
        connection.execute(
            "DELETE FROM mock_test_attempt_reviews WHERE student_id=?",
            (student_id,)
        )
        connection.execute(
            "DELETE FROM mock_test_results WHERE student_id=?",
            (student_id,)
        )
        connection.commit()
    finally:
        connection.close()
    return redirect(url_for("mock_test_history_list"))


# ==========================================
# MOCK TEST HISTORY DETAILS
# ==========================================

@app.route("/mock-test-history/<int:result_id>/delete", methods=["POST"])
def delete_mock_test_history(result_id):
    if "student_id" not in session:
        return redirect(url_for("login"))
    connection = get_db_connection()
    try:
        owned = connection.execute(
            "SELECT id FROM mock_test_results WHERE id=? AND student_id=?",
            (result_id, session["student_id"])
        ).fetchone()
        if owned is None:
            abort(404)
        connection.execute(
            "DELETE FROM mock_test_attempt_reviews WHERE result_id=? AND student_id=?",
            (result_id, session["student_id"])
        )
        connection.execute(
            "DELETE FROM mock_test_results WHERE id=? AND student_id=?",
            (result_id, session["student_id"])
        )
        connection.commit()
    finally:
        connection.close()
    return redirect(url_for("mock_test_history_list"))


@app.route("/mock-test-history/<int:result_id>/download")
def download_mock_test_history(result_id):
    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    try:
        result = connection.execute(
            """SELECT r.id,r.exam_name,r.total_questions,r.correct,r.wrong,
                      r.unanswered,r.score,r.percentage,r.created_at,a.review_json
               FROM mock_test_results r
               LEFT JOIN mock_test_attempt_reviews a
                 ON a.result_id=r.id AND a.student_id=r.student_id
               WHERE r.id=? AND r.student_id=?""",
            (result_id, session["student_id"])
        ).fetchone()
    finally:
        connection.close()

    if result is None:
        abort(404)

    try:
        review = json.loads(result["review_json"]) if result["review_json"] else []
    except (TypeError, ValueError):
        review = []

    buffer = BytesIO()

    # ------------------------------------------------------------
    # Civil Career professional report theme
    # ------------------------------------------------------------
    NAVY = colors.HexColor("#0F172A")
    SLATE = colors.HexColor("#334155")
    MUTED = colors.HexColor("#64748B")
    LIGHT = colors.HexColor("#F8FAFC")
    BORDER = colors.HexColor("#E2E8F0")
    TEAL = colors.HexColor("#0F766E")
    TEAL_LIGHT = colors.HexColor("#CCFBF1")
    GREEN = colors.HexColor("#15803D")
    GREEN_LIGHT = colors.HexColor("#DCFCE7")
    RED = colors.HexColor("#B91C1C")
    RED_LIGHT = colors.HexColor("#FEE2E2")
    AMBER = colors.HexColor("#B45309")
    AMBER_LIGHT = colors.HexColor("#FEF3C7")
    BLUE_LIGHT = colors.HexColor("#DBEAFE")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="CCCoverTitle", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=25, leading=30, textColor=colors.white, spaceAfter=6
    ))
    styles.add(ParagraphStyle(
        name="CCCoverSub", parent=styles["Normal"], fontName="Helvetica",
        fontSize=11, leading=16, textColor=colors.HexColor("#CBD5E1")
    ))
    styles.add(ParagraphStyle(
        name="CCSection", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=15, leading=19, textColor=NAVY, spaceBefore=5, spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name="CCQuestion", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=15, textColor=NAVY, spaceAfter=5
    ))
    styles.add(ParagraphStyle(
        name="CCBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9.2, leading=13.2, textColor=SLATE
    ))
    styles.add(ParagraphStyle(
        name="CCSmall", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=8, leading=10.5, textColor=MUTED
    ))
    styles.add(ParagraphStyle(
        name="CCOption", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9, leading=12.5, textColor=SLATE
    ))
    styles.add(ParagraphStyle(
        name="CCLabel", parent=styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=8, leading=10, textColor=MUTED
    ))
    styles.add(ParagraphStyle(
        name="CCValue", parent=styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=9.2, leading=12, textColor=NAVY
    ))
    styles.add(ParagraphStyle(
        name="CCExplanation", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=8.8, leading=12.5, textColor=SLATE
    ))

    def footer(canvas, doc):
        draw_civilcareer_pdf_chrome(
            canvas, doc,
            header_right=exam_name,
            footer_label=exam_name + " Mock Test Attempt"
        )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=15*mm,
        leftMargin=15*mm,
        topMargin=25*mm,
        bottomMargin=20*mm,
        title="Civil Career - Mock Test Attempt Report",
        author="Civil Career"
    )

    story = []

    exam_name = str(result["exam_name"] or "Mock Test")
    attempt_id = result["id"]
    total = int(result["total_questions"] or 0)
    correct = int(result["correct"] or 0)
    wrong = int(result["wrong"] or 0)
    unanswered = int(result["unanswered"] or 0)
    score = result["score"] or 0
    percentage = float(result["percentage"] or 0)

    # Premium cover/header
    cover = Table(
        [[
            Paragraph("CIVIL CAREER", styles["CCCoverTitle"]),
            Paragraph("MOCK TEST<br/><font size='9'>ATTEMPT REPORT</font>", styles["CCCoverSub"])
        ]],
        colWidths=[105*mm, 65*mm],
        rowHeights=[34*mm]
    )
    cover.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), NAVY),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (0,0), 9*mm),
        ("RIGHTPADDING", (0,0), (-1,-1), 8*mm),
        ("TOPPADDING", (0,0), (-1,-1), 6*mm),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6*mm),
    ]))
    story.append(cover)
    story.append(Spacer(1, 9*mm))

    story.append(Paragraph(escape(exam_name), ParagraphStyle(
        "CCExam", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=22, leading=26, textColor=NAVY, spaceAfter=3
    )))
    story.append(Paragraph("Official saved attempt record", styles["CCSmall"]))
    story.append(Spacer(1, 5*mm))

    meta = Table([
        [Paragraph("<b>ATTEMPT ID</b><br/>%s" % escape(str(attempt_id)), styles["CCValue"]),
         Paragraph("<b>DATE & TIME</b><br/>%s" % escape(format_datetime_ist(result["created_at"], include_seconds=True)), styles["CCValue"])],
        [Paragraph("<b>TOTAL QUESTIONS</b><br/>%s" % total, styles["CCValue"]),
         Paragraph("<b>SCORE</b><br/>%s" % escape(str(score)), styles["CCValue"])]
    ], colWidths=[87*mm, 87*mm])
    meta.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), LIGHT),
        ("BOX", (0,0), (-1,-1), 0.7, BORDER),
        ("INNERGRID", (0,0), (-1,-1), 0.5, BORDER),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 5*mm),
        ("RIGHTPADDING", (0,0), (-1,-1), 5*mm),
        ("TOPPADDING", (0,0), (-1,-1), 4*mm),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4*mm),
    ]))
    story.append(meta)
    story.append(Spacer(1, 5*mm))

    # Two-row summary cards keep the four result metrics readable in every PDF viewer.
    summary_data = [
        [
            Paragraph("<b>CORRECT</b><br/><font size='18'>%s</font>" % correct, styles["CCValue"]),
            Paragraph("<b>WRONG</b><br/><font size='18'>%s</font>" % wrong, styles["CCValue"])
        ],
        [
            Paragraph("<b>UNANSWERED</b><br/><font size='18'>%s</font>" % unanswered, styles["CCValue"]),
            Paragraph("<b>PERCENTAGE</b><br/><font size='18'>%.1f%%</font>" % percentage, styles["CCValue"])
        ]
    ]
    summary = Table(summary_data, colWidths=[87*mm, 87*mm], rowHeights=[20*mm, 20*mm])
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,0), GREEN_LIGHT),
        ("BACKGROUND", (1,0), (1,0), RED_LIGHT),
        ("BACKGROUND", (0,1), (0,1), AMBER_LIGHT),
        ("BACKGROUND", (1,1), (1,1), BLUE_LIGHT),
        ("BOX", (0,0), (-1,-1), 0.7, BORDER),
        ("INNERGRID", (0,0), (-1,-1), 0.5, BORDER),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 4*mm),
        ("RIGHTPADDING", (0,0), (-1,-1), 4*mm),
        ("TOPPADDING", (0,0), (-1,-1), 3*mm),
        ("BOTTOMPADDING", (0,0), (-1,-1), 3*mm),
    ]))
    story.append(summary)

    # Page 1 is a clean attempt summary. Detailed answer review always starts on page 2.
    story.append(PageBreak())
    story.append(Paragraph("Saved Answer Review", styles["CCSection"]))
    story.append(HRFlowable(width="100%", thickness=1, color=TEAL, spaceAfter=7))

    if isinstance(review, list) and review:
        for idx, item in enumerate(review, 1):
            if not isinstance(item, dict):
                story.append(Paragraph(escape(str(item)), styles["CCBody"]))
                continue

            question = item.get("question") or item.get("question_text") or "Question %s" % idx

            option_rows = []
            for letter in ("a", "b", "c", "d"):
                option = item.get("option_" + letter)
                if option not in (None, ""):
                    option_rows.append([
                        Paragraph("<b>%s)</b>" % letter.upper(), styles["CCOption"]),
                        Paragraph(escape(str(option)), styles["CCOption"])
                    ])

            user_answer = item.get("user_answer", item.get("selected_answer"))
            if user_answer in (None, ""):
                user_answer = "Not Answered"
            correct_answer = item.get("correct_answer")
            if correct_answer in (None, ""):
                correct_answer = "Not available"
            status = str(item.get("status") or "unanswered").replace("_", " ").title()

            status_bg = GREEN_LIGHT if status.lower() == "correct" else RED_LIGHT if status.lower() == "wrong" else AMBER_LIGHT

            q_header = Table([[
                Paragraph("<b>Q%s</b>" % idx, ParagraphStyle(
                    "CCQNo", parent=styles["Normal"], fontName="Helvetica-Bold",
                    fontSize=11, textColor=colors.white, alignment=1
                )),
                Paragraph(escape(str(question)), styles["CCQuestion"])
            ]], colWidths=[13*mm, 161*mm])
            q_header.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (0,0), TEAL),
                ("BACKGROUND", (1,0), (1,0), LIGHT),
                ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                ("LEFTPADDING", (0,0), (0,0), 2*mm),
                ("RIGHTPADDING", (0,0), (-1,-1), 3*mm),
                ("TOPPADDING", (0,0), (-1,-1), 3*mm),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3*mm),
                ("BOX", (0,0), (-1,-1), 0.7, BORDER),
            ]))
            story.append(q_header)
            story.append(Spacer(1, 2*mm))

            if option_rows:
                options_table = Table(option_rows, colWidths=[11*mm, 163*mm])
                options_table.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), colors.white),
                    ("BOX", (0,0), (-1,-1), 0.5, BORDER),
                    ("INNERGRID", (0,0), (-1,-1), 0.3, BORDER),
                    ("VALIGN", (0,0), (-1,-1), "TOP"),
                    ("LEFTPADDING", (0,0), (-1,-1), 2.5*mm),
                    ("RIGHTPADDING", (0,0), (-1,-1), 2.5*mm),
                    ("TOPPADDING", (0,0), (-1,-1), 2*mm),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 2*mm),
                ]))
                story.append(options_table)
                story.append(Spacer(1, 2*mm))

            answer_table = Table([[
                Paragraph("<b>Your Answer</b><br/>%s" % escape(str(user_answer)), styles["CCBody"]),
                Paragraph("<b>Correct Answer</b><br/>%s" % escape(str(correct_answer)), styles["CCBody"]),
                Paragraph("<b>Status</b><br/>%s" % escape(status), styles["CCBody"]),
                Paragraph("<b>Marks</b><br/>%s" % escape(str(item.get("marks", "-"))), styles["CCBody"])
            ]], colWidths=[43.5*mm]*4)
            answer_table.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,-1), LIGHT),
                ("BACKGROUND", (2,0), (2,0), status_bg),
                ("BOX", (0,0), (-1,-1), 0.5, BORDER),
                ("INNERGRID", (0,0), (-1,-1), 0.3, BORDER),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING", (0,0), (-1,-1), 2.5*mm),
                ("RIGHTPADDING", (0,0), (-1,-1), 2.5*mm),
                ("TOPPADDING", (0,0), (-1,-1), 2.5*mm),
                ("BOTTOMPADDING", (0,0), (-1,-1), 2.5*mm),
            ]))
            story.append(answer_table)

            topic_parts = []
            if item.get("subject"):
                topic_parts.append(str(item["subject"]))
            if item.get("topic"):
                topic_parts.append(str(item["topic"]))
            if item.get("difficulty_level"):
                topic_parts.append(str(item["difficulty_level"]))
            if topic_parts:
                story.append(Spacer(1, 2*mm))
                story.append(Paragraph(
                    "<b>Topic:</b> %s" % escape("  •  ".join(topic_parts)),
                    styles["CCSmall"]
                ))

            explanation = item.get("explanation")
            solution = item.get("solution")
            if explanation:
                story.append(Spacer(1, 2*mm))
                expl = Table([[
                    Paragraph("<b>EXPLANATION</b><br/>%s" % escape(str(explanation)), styles["CCExplanation"])
                ]], colWidths=[174*mm])
                expl.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), TEAL_LIGHT),
                    ("BOX", (0,0), (-1,-1), 0.5, BORDER),
                    ("LEFTPADDING", (0,0), (-1,-1), 3*mm),
                    ("RIGHTPADDING", (0,0), (-1,-1), 3*mm),
                    ("TOPPADDING", (0,0), (-1,-1), 2.5*mm),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 2.5*mm),
                ]))
                story.append(expl)

            if solution:
                story.append(Spacer(1, 2*mm))
                sol = Table([[
                    Paragraph("<b>SOLUTION</b><br/>%s" % escape(str(solution)), styles["CCExplanation"])
                ]], colWidths=[174*mm])
                sol.setStyle(TableStyle([
                    ("BACKGROUND", (0,0), (-1,-1), LIGHT),
                    ("BOX", (0,0), (-1,-1), 0.5, BORDER),
                    ("LEFTPADDING", (0,0), (-1,-1), 3*mm),
                    ("RIGHTPADDING", (0,0), (-1,-1), 3*mm),
                    ("TOPPADDING", (0,0), (-1,-1), 2.5*mm),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 2.5*mm),
                ]))
                story.append(sol)

            story.append(Spacer(1, 5*mm))
    else:
        story.append(Paragraph(
            "No answer-by-answer review is stored for this historical attempt. The summary above is the saved result. New attempts save the complete question, selected answer, correct answer, status, marks, and explanations.",
            styles["CCBody"]
        ))

    story.append(Spacer(1, 3*mm))
    story.append(HRFlowable(width="100%", thickness=0.7, color=BORDER, spaceBefore=4, spaceAfter=5))
    story.append(Paragraph(
        "Generated by Civil Career • This report reflects the saved attempt data and answer review for this attempt.",
        styles["CCSmall"]
    ))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name="mock_attempt_%s.pdf" % result_id,
        mimetype="application/pdf"
    )


@app.route("/mock-test-history/<int:result_id>")
def mock_test_history_detail(result_id):

    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()

    result = connection.execute(
        """
        SELECT r.id, r.exam_slug, r.exam_name, r.total_questions,
               r.correct, r.wrong, r.unanswered, r.score, r.percentage,
               r.attempt_id, r.created_at, a.review_json
        FROM mock_test_results r
        LEFT JOIN mock_test_attempt_reviews a
          ON a.result_id = r.id AND a.student_id = r.student_id
        WHERE r.id = ? AND r.student_id = ?
        """,
        (result_id, session["student_id"])
    ).fetchone()
    connection.close()

    if result is None:
        return "Mock test result not found", 404

    try:
        saved_review = json.loads(result["review_json"]) if result["review_json"] else []
    except (TypeError, ValueError):
        saved_review = []

    return render_template(
        "mock_history_details.html",
        student_name=session.get("student_name", "Student"),
        student_education=session.get("student_education", ""),
        result=result,
        review=saved_review
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

        {
            "question":
                "The unit weight of water is approximately:",

            "option_a": "1 kN/m³",
            "option_b": "9.81 kN/m³",
            "option_c": "98.1 kN/m³",
            "option_d": "100 kN/m³",

            "correct_answer": "B"
        },

        {
            "question":
                "The Reynolds number is mainly used to determine the nature of:",

            "option_a": "Soil",
            "option_b": "Concrete",
            "option_c": "Fluid flow",
            "option_d": "Road pavement",

            "correct_answer": "C"
        },

        {
            "question":
                "Effective stress in saturated soil is equal to:",

            "option_a": "Total stress + pore pressure",
            "option_b": "Total stress − pore pressure",
            "option_c": "Pore pressure − total stress",
            "option_d": "Total stress × pore pressure",

            "correct_answer": "B"
        },

        {
            "question":
                "The main purpose of providing camber on a road is:",

            "option_a": "Drainage",
            "option_b": "Increasing road length",
            "option_c": "Reducing traffic",
            "option_d": "Increasing pavement thickness",

            "correct_answer": "A"
        },

        {
            "question":
                "The standard unit of coefficient of permeability of soil is:",

            "option_a": "m/s",
            "option_b": "m²/s",
            "option_c": "N/m²",
            "option_d": "kg/m³",

            "correct_answer": "A"
        },

        {
            "question":
                "The slump test is commonly used to measure the workability of:",

            "option_a": "Fresh concrete",
            "option_b": "Hardened concrete",
            "option_c": "Cement paste after setting",
            "option_d": "Bitumen",

            "correct_answer": "A"
        },

        {
            "question":
                "For ordinary concrete, reducing the water-cement ratio generally increases:",

            "option_a": "Permeability",
            "option_b": "Compressive strength",
            "option_c": "Bleeding",
            "option_d": "Segregation in every case",

            "correct_answer": "B"
        },

        {
            "question":
                "The neutral axis of a homogeneous symmetric rectangular beam section passes through its:",

            "option_a": "Top edge",
            "option_b": "Bottom edge",
            "option_c": "Centroid",
            "option_d": "Corner",

            "correct_answer": "C"
        },

        {
            "question":
                "The primary purpose of stirrups in a reinforced concrete beam is to resist:",

            "option_a": "Shear",
            "option_b": "Shrinkage only",
            "option_c": "Temperature only",
            "option_d": "Dead load only",

            "correct_answer": "A"
        },

        {
            "question":
                "In a flow net, the quantity of seepage through a soil foundation is estimated using:",

            "option_a": "Flow channels and equipotential drops",
            "option_b": "Contour intervals only",
            "option_c": "Traffic density",
            "option_d": "Beam deflection",

            "correct_answer": "A"
        },

        {
            "question":
                "A total station is primarily used to measure angles and:",

            "option_a": "Distance electronically",
            "option_b": "Concrete strength",
            "option_c": "Soil moisture only",
            "option_d": "Bitumen viscosity",

            "correct_answer": "A"
        },

        {
            "question":
                "The hydraulic radius of an open channel is the ratio of flow area to:",

            "option_a": "Wetted perimeter",
            "option_b": "Top width",
            "option_c": "Channel slope",
            "option_d": "Hydraulic depth",

            "correct_answer": "A"
        },

        {
            "question":
                "The BOD of wastewater indicates the amount of oxygen required by microorganisms to decompose:",

            "option_a": "Biodegradable organic matter",
            "option_b": "Dissolved sand",
            "option_c": "Chlorine",
            "option_d": "Inert gravel",

            "correct_answer": "A"
        },

        {
            "question":
                "In highway engineering, the main function of a pavement subgrade is to:",

            "option_a": "Provide support to the pavement layers",
            "option_b": "Provide road markings",
            "option_c": "Drain roof water",
            "option_d": "Increase vehicle speed directly",

            "correct_answer": "A"
        },

        {
            "question":
                "A contour line joins points having equal:",

            "option_a": "Elevation",
            "option_b": "Slope distance",
            "option_c": "Bearing",
            "option_d": "Rainfall intensity",

            "correct_answer": "A"
        },

        {
            "question":
                "The critical path in a project network is the path with:",

            "option_a": "The longest total duration",
            "option_b": "The fewest activities",
            "option_c": "The lowest cost only",
            "option_d": "No predecessor activities",

            "correct_answer": "A"
        },

        {
            "question":
                "The California Bearing Ratio test is mainly used to evaluate:",

            "option_a": "Subgrade strength for pavement design",
            "option_b": "Concrete setting time",
            "option_c": "Steel ductility",
            "option_d": "Water quality",

            "correct_answer": "A"
        },

        {
            "question":
                "The factor of safety for a slope is the ratio of resisting forces to:",

            "option_a": "Driving forces",
            "option_b": "Pore volume",
            "option_c": "Rainfall duration",
            "option_d": "Slope length",

            "correct_answer": "A"
        },

        {
            "question":
                "The main purpose of curing concrete is to maintain suitable moisture and temperature for:",

            "option_a": "Cement hydration",
            "option_b": "Aggregate crushing",
            "option_c": "Steel corrosion",
            "option_d": "Surface drying",

            "correct_answer": "A"
        },

        {
            "question":
                "The minimum grade of concrete generally used for reinforced concrete work is:",

            "option_a": "M10",
            "option_b": "M15",
            "option_c": "M20",
            "option_d": "M5",

            "correct_answer": "C"
        },

        {
            "question":
                "The liquid limit of a soil is determined using the:",

            "option_a": "Casagrande apparatus",
            "option_b": "Proctor mould",
            "option_c": "Pycnometer only",
            "option_d": "Vicat apparatus",

            "correct_answer": "A"
        },

        {
            "question":
                "The Darcy-Weisbach equation is used to calculate head loss due to:",

            "option_a": "Friction in pipe flow",
            "option_b": "Evaporation",
            "option_c": "Rainfall",
            "option_d": "Sedimentation",

            "correct_answer": "A"
        },

        {
            "question":
                "The horizontal distance between two successive vehicle positions on a transition curve is called:",

            "option_a": "Shift",
            "option_b": "Tangent length",
            "option_c": "Chainage",
            "option_d": "Camber",

            "correct_answer": "A"
        },

        {
            "question":
                "The primary objective of a building foundation is to transfer loads safely to:",

            "option_a": "The roof",
            "option_b": "The soil",
            "option_c": "The plaster",
            "option_d": "The damp-proof course",

            "correct_answer": "B"
        },

        {
            "question":
                "A water-cement ratio of 0.50 means that the weight of water is what fraction of cement weight?",

            "option_a": "0.05",
            "option_b": "0.50",
            "option_c": "5.0",
            "option_d": "50.0",

            "correct_answer": "B"
        },

        {
            "question":
                "The instrument used to measure differences in elevation between points is a:",

            "option_a": "Level",
            "option_b": "Planimeter",
            "option_c": "Theodolite only",
            "option_d": "Clinometer only",

            "correct_answer": "A"
        },

        {
            "question":
                "The process of removing air voids from freshly placed concrete is called:",

            "option_a": "Vibration",
            "option_b": "Curing",
            "option_c": "Dressing",
            "option_d": "Tempering",

            "correct_answer": "A"
        },

        {
            "question":
                "The pH value of neutral water at room temperature is approximately:",

            "option_a": "2",
            "option_b": "5",
            "option_c": "7",
            "option_d": "12",

            "correct_answer": "C"
        },

        {
            "question":
                "In a simply supported beam, the bending moment at an ideal pin or roller support is:",

            "option_a": "Zero",
            "option_b": "Maximum always",
            "option_c": "Equal to the shear force",
            "option_d": "Infinite",

            "correct_answer": "A"
        }

    ]

}


MOCK_TEST_QUESTIONS = {
    exam_slug: questions.copy()
    for exam_slug, questions in PYQ_QUESTIONS.items()
}


for exam_questions in MOCK_TEST_QUESTIONS.values():

    for question_index, question in enumerate(exam_questions):

        question["marks"] = 1 if question_index % 2 == 0 else 2


MOCK_TEST_QUESTIONS["gate"][1]["question_type"] = "fill_blank"
MOCK_TEST_QUESTIONS["gate"][1]["answer"] = "9.81"

MOCK_TEST_QUESTIONS["gate"][2]["question_type"] = "msq"
MOCK_TEST_QUESTIONS["gate"][2]["option_a"] = (
    "Effective stress is total stress plus pore pressure"
)
MOCK_TEST_QUESTIONS["gate"][2]["option_b"] = (
    "Effective stress is total stress minus pore pressure"
)
MOCK_TEST_QUESTIONS["gate"][2]["option_c"] = (
    "Pore pressure reduces effective stress"
)
MOCK_TEST_QUESTIONS["gate"][2]["option_d"] = (
    "Effective stress is independent of pore pressure"
)
MOCK_TEST_QUESTIONS["gate"][2]["correct_answer"] = ["B", "C"]

MOCK_TEST_QUESTIONS["gate"].append({
    "question": "A discharge of 2 m³ flows through a channel in 4 seconds. The discharge rate is ___ m³/s.",
    "question_type": "numerical",
    "answer": 0.5,
    "option_a": "",
    "option_b": "",
    "option_c": "",
    "option_d": "",
    "correct_answer": "0.5",
    "marks": 2
})


MOCK_TEST_QUESTIONS["gate"].extend([
    {
        "question": "For a matrix to have an inverse, its determinant must be:",
        "option_a": "Zero",
        "option_b": "Non-zero",
        "option_c": "Negative only",
        "option_d": "Equal to one only",
        "correct_answer": "B"
    },
    {
        "question": "The degree of a polynomial equation is equal to the number of its:",
        "option_a": "Distinct real roots always",
        "option_b": "Roots including multiplicity over the complex field",
        "option_c": "Positive roots only",
        "option_d": "Negative roots only",
        "correct_answer": "B"
    },
    {
        "question": "The bending equation for a beam in elastic bending is:",
        "option_a": "M/I = sigma/y = E/R",
        "option_b": "M/I = y/sigma = R/E",
        "option_c": "M = I/E",
        "option_d": "sigma = MR",
        "correct_answer": "A"
    },
    {
        "question": "In a truss, a member carrying zero force under a particular loading is called a:",
        "option_a": "Redundant member",
        "option_b": "Zero-force member",
        "option_c": "Tension-only member",
        "option_d": "Compression block",
        "correct_answer": "B"
    },
    {
        "question": "The characteristic strength of concrete is defined at an age of:",
        "option_a": "3 days",
        "option_b": "7 days",
        "option_c": "14 days",
        "option_d": "28 days",
        "correct_answer": "D"
    },
    {
        "question": "The fineness modulus is an index of the average size of particles in:",
        "option_a": "Fine or coarse aggregate",
        "option_b": "Cement paste only",
        "option_c": "Structural steel",
        "option_d": "Fresh concrete only",
        "correct_answer": "A"
    },
    {
        "question": "The standard Proctor test is used to determine the relationship between moisture content and:",
        "option_a": "Dry density of soil",
        "option_b": "Liquid limit only",
        "option_c": "Permeability only",
        "option_d": "Shear strength of steel",
        "correct_answer": "A"
    },
    {
        "question": "According to Darcy's law, seepage velocity through soil is proportional to the:",
        "option_a": "Hydraulic gradient",
        "option_b": "Specific gravity only",
        "option_c": "Grain diameter squared only",
        "option_d": "Atmospheric pressure",
        "correct_answer": "A"
    },
    {
        "question": "The active earth pressure condition occurs when a retaining wall moves:",
        "option_a": "Towards the backfill",
        "option_b": "Away from the backfill",
        "option_c": "Vertically upward only",
        "option_d": "Without any deformation",
        "correct_answer": "B"
    },
    {
        "question": "The Froude number is important in the analysis of:",
        "option_a": "Open channel flow",
        "option_b": "Soil classification",
        "option_c": "Concrete strength",
        "option_d": "Steel corrosion",
        "correct_answer": "A"
    },
    {
        "question": "For uniform flow in an open channel, the energy slope is equal to the:",
        "option_a": "Bed slope",
        "option_b": "Side slope only",
        "option_c": "Cross-fall",
        "option_d": "Bank height",
        "correct_answer": "A"
    },
    {
        "question": "The main purpose of a spillway in a reservoir is to:",
        "option_a": "Release excess flood water safely",
        "option_b": "Increase sediment deposition",
        "option_c": "Measure cement fineness",
        "option_d": "Support bridge traffic",
        "correct_answer": "A"
    },
    {
        "question": "The activated sludge process is a method of:",
        "option_a": "Secondary wastewater treatment",
        "option_b": "Water distribution only",
        "option_c": "Solid waste landfilling",
        "option_d": "Road construction",
        "correct_answer": "A"
    },
    {
        "question": "The main objective of chlorination of drinking water is:",
        "option_a": "Disinfection",
        "option_b": "Softening only",
        "option_c": "Increasing turbidity",
        "option_d": "Removing all dissolved salts",
        "correct_answer": "A"
    },
    {
        "question": "Superelevation on a horizontal road curve is provided to counteract:",
        "option_a": "Centrifugal force",
        "option_b": "Vehicle weight only",
        "option_c": "Rolling resistance only",
        "option_d": "Wind pressure only",
        "correct_answer": "A"
    },
    {
        "question": "The stopping sight distance of a vehicle depends mainly on speed, reaction time, and:",
        "option_a": "Braking distance",
        "option_b": "Pavement colour",
        "option_c": "Lane marking width only",
        "option_d": "Shoulder material only",
        "correct_answer": "A"
    },
    {
        "question": "The purpose of a transition curve is to provide a gradual change in:",
        "option_a": "Curvature and superelevation",
        "option_b": "Pavement colour",
        "option_c": "Traffic signal timing",
        "option_d": "Soil classification",
        "correct_answer": "A"
    },
    {
        "question": "In surveying, a benchmark is a point whose elevation is:",
        "option_a": "Known or established",
        "option_b": "Always zero",
        "option_c": "Equal to its bearing",
        "option_d": "Estimated from rainfall",
        "correct_answer": "A"
    },
    {
        "question": "The contour interval is the constant difference in elevation between:",
        "option_a": "Successive contour lines",
        "option_b": "Two benchmarks only",
        "option_c": "Two road lanes",
        "option_d": "Two survey stations only",
        "correct_answer": "A"
    },
    {
        "question": "In project scheduling, total float is the time by which an activity can be delayed without delaying:",
        "option_a": "Project completion",
        "option_b": "Its own start date",
        "option_c": "Material delivery only",
        "option_d": "The site survey only",
        "correct_answer": "A"
    }
])


for exam_questions in MOCK_TEST_QUESTIONS.values():

    for question_index, question in enumerate(exam_questions):

        question.setdefault("question_type", "mcq")
        question.setdefault("marks", 1 if question_index % 2 == 0 else 2)


for exam_slug, exam_questions in MOCK_TEST_QUESTIONS.items():

    if exam_slug == "gate" or len(exam_questions) < 2:
        continue

    fill_question = exam_questions[1]
    correct_option = fill_question["correct_answer"].lower()
    fill_question["question_type"] = "fill_blank"
    fill_question["answer"] = fill_question[
        "option_" + correct_option
    ]


# SSC JE Civil CBT practice bank.
# /pyqs/ssc-je remains the separate 5-question PYQ page.
# This compact CBT uses 30 Civil Engineering MCQs; these added questions
# are Civil Career practice questions, not labeled as official PYQs.
SSC_JE_CBT_EXTRA = [
    ("The standard Proctor test is used to determine the relationship between:", "Moisture content and dry density", "Stress and strain", "Flow and pressure", "Load and deflection", "A", "Geotechnical Engineering", "Compaction"),
    ("Darcy's law is applicable to:", "Laminar flow through soil", "Turbulent flow in open channels", "Concrete mixing", "Steel welding", "A", "Geotechnical Engineering", "Permeability"),
    ("The neutral axis of a homogeneous symmetrical rectangular beam passes through its:", "Top edge", "Bottom edge", "Centroid", "Corner", "C", "Strength of Materials", "Bending"),
    ("The bending moment at an ideal simple support of a simply supported beam is:", "Zero", "Maximum", "Infinite", "Equal to shear force", "A", "Strength of Materials", "Bending Moment"),
    ("The primary purpose of stirrups in an RCC beam is to resist:", "Shear", "Dead load only", "Temperature only", "Creep only", "A", "RCC", "Shear Reinforcement"),
    ("The characteristic compressive strength of concrete is normally specified at an age of:", "3 days", "7 days", "28 days", "90 days", "C", "Concrete Technology", "Concrete Strength"),
    ("The specific gravity of cement is approximately:", "1.0", "2.0", "3.15", "5.0", "C", "Construction Materials", "Cement"),
    ("The initial setting time of ordinary Portland cement should not be less than:", "10 minutes", "30 minutes", "60 minutes", "120 minutes", "B", "Construction Materials", "Cement Setting"),
    ("The instrument primarily used for measuring horizontal and vertical angles is:", "Theodolite", "Planimeter", "Rain gauge", "Proctor mould", "A", "Surveying", "Theodolite"),
    ("A benchmark in surveying is a point of known:", "Bearing", "Reduced level", "Chainage only", "Area", "B", "Surveying", "Levelling"),
    ("The hydraulic radius of an open channel is the ratio of flow area to:", "Wetted perimeter", "Top width", "Channel slope", "Hydraulic depth", "A", "Fluid Mechanics", "Open Channel Flow"),
    ("Reynolds number is mainly used to identify the nature of:", "Soil", "Concrete", "Fluid flow", "Road pavement", "C", "Fluid Mechanics", "Flow Regime"),
    ("Bernoulli's equation is based on conservation of:", "Mass", "Energy", "Momentum only", "Temperature", "B", "Fluid Mechanics", "Bernoulli Equation"),
    ("BOD of wastewater is an indicator of:", "Biodegradable organic pollution", "Hardness only", "Chloride concentration only", "Turbidity only", "A", "Environmental Engineering", "Wastewater Characteristics"),
    ("The pH of neutral water at about room temperature is approximately:", "2", "5", "7", "12", "C", "Environmental Engineering", "Water Quality"),
    ("The main purpose of a foundation is to safely transfer structural load to:", "Roof", "Soil", "Plaster", "Ceiling", "B", "Geotechnical Engineering", "Foundations"),
    ("A retaining wall is primarily constructed to retain:", "Soil", "Steel", "Timber", "Roof tiles", "A", "Geotechnical Engineering", "Earth Retaining Structures"),
    ("The California Bearing Ratio (CBR) test is mainly used in:", "Pavement design", "Steel design", "Water treatment", "Concrete setting", "A", "Transportation Engineering", "Pavement Design"),
    ("The primary function of a road pavement subgrade is to:", "Provide support to pavement layers", "Provide road markings", "Increase vehicle speed", "Store rainwater", "A", "Transportation Engineering", "Pavement Components"),
    ("The critical path in a project network is the path having:", "Longest total duration", "Shortest duration", "Lowest cost only", "Fewest activities", "A", "Construction Management", "CPM"),
    ("The main purpose of curing concrete is to provide suitable conditions for:", "Cement hydration", "Aggregate crushing", "Steel cutting", "Surface drying", "A", "Concrete Technology", "Curing"),
    ("For a homogeneous isotropic material in the elastic range, Young's modulus is the ratio of:", "Normal stress to normal strain", "Shear stress to shear strain", "Load to moment", "Moment to area", "A", "Strength of Materials", "Elastic Constants"),
    ("The process of removing entrapped air from freshly placed concrete is called:", "Compaction", "Curing", "Segregation", "Bleeding", "A", "Concrete Technology", "Compaction"),
    ("The water-cement ratio is defined as the ratio of the weight of water to the weight of:", "Fine aggregate", "Cement", "Coarse aggregate", "Concrete", "B", "Concrete Technology", "Mix Proportioning"),
    ("Superelevation on a horizontal road curve is provided mainly to counteract:", "Centrifugal force", "Vehicle weight only", "Rolling resistance only", "Wind pressure only", "A", "Transportation Engineering", "Superelevation"),
]

SSC_JE_MOCK_QUESTIONS = []
for row in SSC_JE_CBT_EXTRA:
    question_text, option_a, option_b, option_c, option_d, correct, subject, topic = row
    SSC_JE_MOCK_QUESTIONS.append({
        "question": question_text,
        "option_a": option_a,
        "option_b": option_b,
        "option_c": option_c,
        "option_d": option_d,
        "correct_answer": correct,
        "subject": subject,
        "topic": topic,
        "explanation": "This Civil Career practice question checks the standard SSC JE Civil concept for this topic.",
        "solution": "Select option %s." % correct,
        "question_type": "mcq",
        "marks": 1,
    })

# The first 5 are the existing SSC JE question set; the 25 above make the
# compact CBT exactly 30 questions / 30 marks.
SSC_JE_MOCK_QUESTIONS = MOCK_TEST_QUESTIONS["ssc-je"] + SSC_JE_MOCK_QUESTIONS
for q in SSC_JE_MOCK_QUESTIONS:
    q["marks"] = 1
    q["question_type"] = "mcq"
MOCK_TEST_QUESTIONS["ssc-je"] = SSC_JE_MOCK_QUESTIONS

def answer_is_correct(question, user_answer):

    question_type = question.get("question_type", "mcq")

    if question_type == "msq":
        return sorted(user_answer or []) == sorted(question["correct_answer"])

    if question_type in ("fill_blank", "numerical", "nat"):
        try:
            return abs(
                float(str(user_answer).strip()) - float(question["answer"])
            ) <= 0.01
        except (TypeError, ValueError):
            return str(user_answer).strip().lower() == str(
                question["answer"]
            ).strip().lower()

    return user_answer == question["correct_answer"]

# ==========================================
# MOCK TEST ENGINE
# ==========================================

MOCK_TEST_DURATIONS = {
    "gate": 180 * 60,
    "ssc-je": 30 * 60,
    "je-ae": 30 * 60,
    "diploma": 30 * 60,
    "btech": 30 * 60,
    "government": 30 * 60,
}


@app.route(
    "/mock-test/<exam_slug>",
    methods=["GET", "POST"]
)
def mock_test(exam_slug):

    # ==========================================
    # LOGIN CHECK
    # ==========================================

    if "student_id" not in session:
        return redirect(url_for("login"))


    # ==========================================
    # EXAM CHECK
    # ==========================================

    if exam_slug not in MOCK_TEST_QUESTIONS:
        return "Mock test not available", 404


    # ==========================================
    # SESSION KEYS
    # ==========================================

    index_key = "mock_index_" + exam_slug
    answers_key = "mock_answers_" + exam_slug
    timer_key = "mock_deadline_" + exam_slug
    order_key = "mock_order_" + exam_slug
    seen_key = "mock_seen_" + exam_slug
    doubt_key = "mock_doubt_" + exam_slug
    fullscreen_key = "mock_fullscreen_started_" + exam_slug
    attempt_key = "mock_attempt_" + exam_slug
    completed_result_key = "mock_completed_result_id_" + exam_slug

    mode_key = "mock_mode_" + exam_slug
    profile_key = "mock_profile_" + exam_slug
    scope_key = "mock_scope_" + exam_slug
    count_key = "mock_count_" + exam_slug
    syllabus_year_key = "mock_syllabus_year_" + exam_slug


    # ==========================================
    # REQUESTED GATE SETTINGS
    # ==========================================

    requested_mode = request.args.get(
        "mode",
        session.get(mode_key, "mixed")
    )

    requested_profile = request.args.get(
        "profile",
        session.get(profile_key, "full")
    )

    requested_scope = request.args.get(
        "scope",
        session.get(scope_key, "all")
    )

    requested_count = request.args.get(
        "count",
        session.get(count_key, 0),
        type=int
    )

    requested_syllabus_year = request.args.get(
        "syllabus_year",
        session.get(syllabus_year_key, "2026")
    )
    if requested_syllabus_year not in GATE_SYLLABI:
        requested_syllabus_year = "2026"


    # ==========================================
    # VALIDATE SETTINGS
    # ==========================================

    allowed_profiles = {
        "short",
        "standard",
        "full",
        "difficult",
        "expert",
        "elite"
    }

    allowed_scopes = {
        "all",
        "mathematics",
        "core",
        "aptitude"
    }

    if requested_profile not in allowed_profiles:
        requested_profile = "full"

    if requested_scope not in allowed_scopes:
        requested_scope = "all"

    if requested_count < 0 or requested_count > 100:
        requested_count = 0


    # ==========================================
    # DETERMINE NEW TEST
    # ==========================================

    start_new = (
        request.args.get("new") == "1"
        or bool(session.get(completed_result_key))
    )


    # ==========================================
    # LOAD QUESTIONS
    # ==========================================

    if exam_slug == "gate":

        questions_key = "mock_questions_" + exam_slug
        attempt_no_key = "mock_attempt_no_" + exam_slug
        last_questions_key = "mock_last_questions_" + exam_slug

        if start_new or "mock_seed_" + exam_slug not in session or count_key not in session:
            # Keep the Flask cookie session compact. Full question objects are
            # rebuilt deterministically from the attempt seed on every request.
            previous_seed = session.get("mock_last_seed_" + exam_slug)
            previous_count = int(session.get("mock_last_count_" + exam_slug, 0) or 0)
            previous_fps = []
            if previous_seed and previous_count:
                previous_questions = build_gate_mock(
                    mode="mixed", count=previous_count, profile=None,
                    scope="all", attempt_seed=previous_seed
                )
                previous_fps = [_question_fingerprint(q) for q in previous_questions]

            attempt_no = int(session.get(attempt_no_key, 0)) + 1
            count_cycle = [65]
            target_count = count_cycle[(attempt_no - 1) % len(count_cycle)]
            attempt_seed = uuid.uuid4().hex

            session["mock_last_seed_" + exam_slug] = attempt_seed
            session["mock_last_count_" + exam_slug] = target_count
            session["mock_seed_" + exam_slug] = attempt_seed
            session[attempt_no_key] = attempt_no
            session[count_key] = target_count

            questions = build_gate_mock(
                mode="mixed", count=target_count, profile=None,
                scope="all", avoid_fingerprints=previous_fps,
                attempt_seed=attempt_seed
            )
        else:
            attempt_seed = session.get("mock_seed_" + exam_slug)
            target_count = int(session.get(count_key, 60) or 60)
            questions = build_gate_mock(
                mode="mixed", count=target_count, profile=None,
                scope="all", attempt_seed=attempt_seed
            )

    # ==========================================
    # NEW ATTEMPT
    # ==========================================

    if (
        start_new
        or timer_key not in session
        or order_key not in session
        or answers_key not in session
    ):

        # A completed attempt must never be reused for a later test.
        session.pop(completed_result_key, None)

        # --------------------------------------
        # TIMER = 180 MINUTES
        # --------------------------------------

        session[timer_key] = (
            int(time.time())
            + MOCK_TEST_DURATIONS.get(
                exam_slug,
                30 * 60
            )
        )

        # Store the real start time for the downloadable result report.
        session["mock_started_at_" + exam_slug] = int(time.time())


        # --------------------------------------
        # START AT QUESTION 1
        # --------------------------------------

        session[index_key] = 0


        # --------------------------------------
        # EMPTY ANSWERS
        # --------------------------------------

        session[answers_key] = {}


        # --------------------------------------
        # EMPTY SEEN QUESTIONS
        # --------------------------------------

        session[seen_key] = []


        # --------------------------------------
        # EMPTY REVIEW LIST
        # --------------------------------------

        session[doubt_key] = []


        # --------------------------------------
        # FULLSCREEN
        # --------------------------------------

        session[fullscreen_key] = False


        # --------------------------------------
        # NEW UNIQUE ATTEMPT ID
        # --------------------------------------

        session[attempt_key] = str(
            uuid.uuid4()
        )


        # --------------------------------------
        # RANDOM QUESTION ORDER
        #
        # random.sample() guarantees that the
        # same question is not selected twice
        # in this attempt.
        # --------------------------------------

        question_order = random.sample(
            range(len(questions)),
            len(questions)
        )

        session[order_key] = question_order


    else:

        question_order = session.get(
            order_key,
            []
        )


    # ==========================================
    # SAFETY CHECK QUESTION ORDER
    # ==========================================

    if (
        not question_order
        or len(question_order) != len(questions)
        or any(
            i < 0 or i >= len(questions)
            for i in question_order
        )
    ):

        question_order = random.sample(
            range(len(questions)),
            len(questions)
        )

        session[order_key] = question_order


    # ==========================================
    # REMAINING TIME
    # ==========================================

    remaining_seconds = (
        session[timer_key]
        - int(time.time())
    )


    # ==========================================
    # TIME EXPIRED
    # ==========================================

    if remaining_seconds <= 0:

        return redirect(
            url_for(
                "mock_test_result",
                exam_slug=exam_slug
            )
        )


    # ==========================================
    # INITIALIZE SESSION VALUES
    # ==========================================

    if index_key not in session:
        session[index_key] = 0

    if answers_key not in session:
        session[answers_key] = {}

    if seen_key not in session:
        session[seen_key] = []

    if doubt_key not in session:
        session[doubt_key] = []


    # ==========================================
    # CURRENT INDEX SAFETY
    # ==========================================

    current_index = session[index_key]

    if (
        current_index < 0
        or current_index >= len(question_order)
    ):

        current_index = 0
        session[index_key] = 0


    # ==========================================
    # HANDLE POST
    # ==========================================

    if request.method == "POST":

        action = request.form.get(
            "action",
            ""
        )

        current_index = session[index_key]

        current_question = questions[
            question_order[current_index]
        ]

        answers = session[answers_key]


        # ======================================
        # SAVE CURRENT ANSWER
        # ======================================

        submitted_answers = request.form.getlist(
            "answer"
        )


        if current_question.get(
            "question_type",
            "mcq"
        ) == "msq":

            if submitted_answers:

                answers[
                    str(current_index)
                ] = submitted_answers

            else:

                answers[
                    str(current_index)
                ] = []

        else:

            answer = request.form.get(
                "answer"
            )

            if answer is not None:

                answers[
                    str(current_index)
                ] = answer


        # ======================================
        # SAVE ALL ANSWERS FROM JS
        # ======================================

        answers_json = request.form.get(
            "answers_json",
            ""
        )


        if answers_json:

            try:

                saved_answers = json.loads(
                    answers_json
                )

                if isinstance(
                    saved_answers,
                    dict
                ):

                    for key, value in saved_answers.items():

                        try:

                            answer_index = int(key)

                            if (
                                answer_index < 0
                                or answer_index >= len(
                                    question_order
                                )
                            ):
                                continue

                            question_for_answer = questions[
                                question_order[
                                    answer_index
                                ]
                            ]

                            if question_for_answer.get(
                                "question_type",
                                "mcq"
                            ) == "msq":

                                if isinstance(
                                    value,
                                    list
                                ):
                                    answers[key] = value

                            else:

                                if isinstance(
                                    value,
                                    list
                                ):

                                    answers[key] = (
                                        value[0]
                                        if value
                                        else ""
                                    )

                                else:

                                    answers[key] = value

                        except (
                            ValueError,
                            TypeError,
                            IndexError
                        ):
                            continue

            except (
                TypeError,
                json.JSONDecodeError
            ):

                pass


        session[answers_key] = answers


        # ======================================
        # MARK / UNMARK FOR REVIEW
        # ======================================

        if action == "toggle_doubt":

            doubt_questions = session[
                doubt_key
            ]

            if current_index in doubt_questions:

                doubt_questions.remove(
                    current_index
                )

            else:

                doubt_questions.append(
                    current_index
                )

            session[doubt_key] = doubt_questions


        # ======================================
        # DIRECT QUESTION NAVIGATION
        # ======================================

        elif action.startswith("goto:"):
            try:
                target_index = int(action.split(":", 1)[1])
            except (TypeError, ValueError):
                target_index = current_index

            if 0 <= target_index < len(question_order):
                session[index_key] = target_index

        # ======================================
        # NEXT
        # ======================================

        elif action == "next":

            if (
                current_index
                < len(question_order) - 1
            ):

                session[index_key] = (
                    current_index + 1
                )


        # ======================================
        # PREVIOUS
        # ======================================

        elif action == "previous":

            if current_index > 0:
                session[index_key] = current_index - 1

        # ======================================
        # SUBMIT
        # ======================================

        elif action == "submit":
            return redirect(
                url_for(
                "mock_test_result",
                exam_slug=exam_slug
            )
        )


    # ==========================================
    # UPDATE CURRENT INDEX
    # ==========================================

    current_index = session[index_key]


    # ==========================================
    # MARK QUESTION AS SEEN
    # ==========================================

    seen_questions = session[seen_key]

    if current_index not in seen_questions:

        seen_questions.append(
            current_index
        )

        session[seen_key] = seen_questions


    # ==========================================
    # CURRENT QUESTION
    # ==========================================

    question = questions[
        question_order[current_index]
    ]


    # ==========================================
    # ANSWERS
    # ==========================================

    answers = session.get(
        answers_key,
        {}
    )


    selected_answer = answers.get(
        str(current_index)
    )


    # ==========================================
    # QUESTION STATUS
    # ==========================================

    question_statuses = []

    for number in range(
        len(question_order)
    ):

        if number == current_index:

            # Keep the review state visible even while the question
            # is currently open.
            if number in session.get(
                doubt_key,
                []
            ):
                status = "current review"
            else:
                status = "current"

        elif number in session.get(
            doubt_key,
            []
        ):

            # Review status must remain visible even if an answer
            # has also been saved for this question.
            status = "review"

        elif str(number) in answers:

            saved = answers[
                str(number)
            ]

            if saved:

                status = "answered"

            else:

                status = "not-answered"

        elif number in session.get(
            seen_key,
            []
        ):

            status = "not-answered"

        else:

            status = "not-visited"


        question_statuses.append(
            status
        )


    # ==========================================
    # EXAM NAME
    # ==========================================

    exam_names = {

        "gate":
            "GATE",

        "ssc-je":
            "SSC JE",

        "je-ae":
            "JE / AE",

        "diploma":
            "Diploma Civil",

        "btech":
            "B.Tech Civil",

        "government":
            "Government Exams"

    }


    exam_name = exam_names.get(

        exam_slug,

        exam_slug.replace(
            "-",
            " "
        ).upper()

    )


    # ==========================================
    # RENDER
    # ==========================================

    return render_template(

        "mock_test.html",

        student_name=session[
            "student_name"
        ],

        student_education=session[
            "student_education"
        ],

        exam_name=exam_name,

        exam_slug=exam_slug,

        question=question,

        question_number=current_index + 1,

        question_index=current_index,

        total_questions=len(
            question_order
        ),

        selected_answer=selected_answer,

        remaining_seconds=remaining_seconds,

        show_start_gate=not session.get(
            fullscreen_key,
            False
        ),

        question_statuses=question_statuses,

        is_doubt=current_index in session.get(
            doubt_key,
            []
        ),

        answered_questions=[
            i
            for i, status
            in enumerate(
                question_statuses,
                start=1
            )
            if status == "answered"
        ],

        review_questions=[
            i
            for i, status
            in enumerate(
                question_statuses,
                start=1
            )
            if "review" in status
        ],

        duration_minutes=round(
            MOCK_TEST_DURATIONS.get(
                exam_slug,
                30 * 60
            ) / 60
        )

    )

@app.route("/mock-test/<exam_slug>/start", methods=["POST"])
def mock_test_start(exam_slug):

    if "student_id" not in session:
        return "Unauthorized", 401

    if exam_slug not in MOCK_TEST_QUESTIONS:
        return "Mock test not available", 404

    session["mock_fullscreen_started_" + exam_slug] = True

    return "", 204


@app.route("/mock-test/<exam_slug>/question/<int:question_index>")
def mock_test_question(
    exam_slug,
    question_index
):

    if "student_id" not in session:
        return redirect(url_for("login"))

    if exam_slug not in MOCK_TEST_QUESTIONS:
        return "Mock test not available", 404

    questions = (
        session.get("mock_questions_" + exam_slug, [])
        if exam_slug == "gate"
        else MOCK_TEST_QUESTIONS[exam_slug]
    )

    order_key = "mock_order_" + exam_slug

    question_order = session.get(order_key, list(range(len(questions))))

    if question_index < 0 or question_index >= len(question_order):
        return redirect(
            url_for(
                "mock_test",
                exam_slug=exam_slug
            )
        )

    session[
        "mock_index_" + exam_slug
    ] = question_index

    return redirect(
        url_for(
            "mock_test",
            exam_slug=exam_slug
        )
    )


# =========================================================
# MOCK TEST RESULT
# =========================================================

@app.route("/mock-test/<exam_slug>/result", methods=["GET", "POST"])
def mock_test_result(exam_slug):

    # =====================================================
    # LOGIN CHECK
    # =====================================================

    if "student_id" not in session:
        return redirect(url_for("login"))

    # =====================================================
    # CHECK EXAM
    # =====================================================

    if exam_slug not in MOCK_TEST_QUESTIONS:
        return "Mock test not available", 404

    # A completed attempt is immutable. Re-opening its result page must
    # show the database snapshot for that exact attempt instead of rebuilding
    # a fresh/random question set (especially important for GATE).
    completed_result_id = session.get("mock_completed_result_id_" + exam_slug)
    if request.method == "GET" and completed_result_id:
        return redirect(url_for("mock_test_history_detail", result_id=int(completed_result_id)))

    # =====================================================
    # FEEDBACK
    # =====================================================

    feedback_key = "mock_feedback_submitted_" + exam_slug

    feedback_submitted = session.get(
        feedback_key,
        False
    )

    if request.method == "POST" and not feedback_submitted:

        rating = request.form.get(
            "rating",
            type=int
        )

        comments = request.form.get(
            "comments",
            ""
        ).strip()

        if rating in range(1, 6) and comments:

            connection = get_db_connection()

            connection.execute(
                """
                INSERT INTO mock_test_feedback
                (
                    student_id,
                    exam_slug,
                    rating,
                    comments
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    session["student_id"],
                    exam_slug,
                    rating,
                    comments
                )
            )

            connection.commit()
            connection.close()

            feedback_submitted = True
            session[feedback_key] = True

            # Release the site-wide feedback redirect after valid submission.
            # Without clearing this key, every other page is redirected back
            # to the mock result page for the completed exam.
            if session.get("mock_feedback_pending_exam") == exam_slug:
                session.pop("mock_feedback_pending_exam", None)

    # =====================================================
    # LOAD QUESTIONS
    # =====================================================

    if exam_slug == "gate":
        questions = session.get(
            "mock_questions_" + exam_slug,
            []
        )
        if not questions:
            questions = build_gate_mock(
                mode="mixed",
                count=65,
                profile=None,
                scope="all",
                avoid_fingerprints=[],
                attempt_seed=uuid.uuid4().hex,
            )
    else:

        questions = MOCK_TEST_QUESTIONS[exam_slug]

    # =====================================================
    # ANSWERS
    # =====================================================

    answers_key = "mock_answers_" + exam_slug

    answers = session.get(
        answers_key,
        {}
    )

    # =====================================================
    # QUESTION ORDER
    # =====================================================

    order_key = "mock_order_" + exam_slug

    question_order = session.get(
        order_key,
        list(range(len(questions)))
    )

    # =====================================================
    # RESULT VARIABLES
    # =====================================================

    correct = 0
    wrong = 0
    unanswered = 0

    total = len(question_order)

    # =====================================================
    # MAXIMUM SCORE
    # =====================================================

    maximum_score = sum(

        questions[question_index].get(
            "marks",
            1
        )

        for question_index in question_order

    )

    score = 0

    # =====================================================
    # STATISTICS
    # =====================================================

    subject_stats = {}
    topic_stats = {}
    difficulty_stats = {}

    # =====================================================
    # ANSWER REVIEW
    # =====================================================

    review = []

    for i, question_index in enumerate(question_order):

        question = questions[question_index]

        user_answer = answers.get(
            str(i)
        )

        correct_answer = question.get(
            "correct_answer",
            ""
        )

        # =================================================
        # DISPLAYED ANSWER
        # =================================================

        if question.get("question_type") in (
            "fill_blank",
            "numerical"
        ):

            displayed_answer = question.get(
                "answer",
                correct_answer
            )

        else:

            displayed_answer = correct_answer

        # =================================================
        # CHECK ANSWER
        # =================================================

        if not user_answer:

            unanswered += 1

            status = "unanswered"

        elif answer_is_correct(
            question,
            user_answer
        ):

            correct += 1

            score += question.get(
                "marks",
                1
            )

            status = "correct"

        else:

            wrong += 1

            # Negative marking:
            # GATE: 1-mark MCQ = -1/3, 2-mark MCQ = -2/3.
            # SSC JE Paper-I: -0.25 for every wrong MCQ.
            if (
                exam_slug == "gate"
                and question.get("question_type", "mcq") == "mcq"
            ):
                score -= (
                    question.get("marks", 1) / 3
                )
            elif (
                exam_slug == "ssc-je"
                and question.get("question_type", "mcq") == "mcq"
            ):
                score -= 0.25

            status = "wrong"

        # =================================================
        # SUBJECT STATISTICS
        # =================================================

        subject_name = question.get(
            "subject",
            "Unclassified"
        )

        subject_row = subject_stats.setdefault(
            subject_name,
            {
                "total": 0,
                "correct": 0,
                "attempted": 0
            }
        )

        subject_row["total"] += 1

        if user_answer:
            subject_row["attempted"] += 1

        if status == "correct":
            subject_row["correct"] += 1

        # =================================================
        # TOPIC STATISTICS
        # =================================================

        topic_name = question.get(
            "topic",
            "Unclassified"
        )

        topic_row = topic_stats.setdefault(
            topic_name,
            {
                "total": 0,
                "correct": 0,
                "attempted": 0
            }
        )

        topic_row["total"] += 1

        if user_answer:
            topic_row["attempted"] += 1

        if status == "correct":
            topic_row["correct"] += 1

        # =================================================
        # DIFFICULTY STATISTICS
        # =================================================

        difficulty_name = question.get(
            "difficulty_level",
            "Unrated"
        )

        difficulty_row = difficulty_stats.setdefault(
            difficulty_name,
            {
                "total": 0,
                "correct": 0,
                "attempted": 0
            }
        )

        difficulty_row["total"] += 1

        if user_answer:
            difficulty_row["attempted"] += 1

        if status == "correct":
            difficulty_row["correct"] += 1

        # =================================================
        # REVIEW DATA
        # =================================================

        review.append({

            "number": i + 1,

            "question": question.get(
                "question",
                ""
            ),

            "option_a": question.get(
                "option_a",
                ""
            ),

            "option_b": question.get(
                "option_b",
                ""
            ),

            "option_c": question.get(
                "option_c",
                ""
            ),

            "option_d": question.get(
                "option_d",
                ""
            ),

            "user_answer": user_answer,

            "correct_answer": displayed_answer,

            "marks": question.get(
                "marks",
                1
            ),

            "question_type": question.get(
                "question_type",
                "mcq"
            ),

            "subject": question.get(
                "subject",
                ""
            ),

            "topic": question.get(
                "topic",
                ""
            ),

            "difficulty_level": question.get(
                "difficulty_level",
                ""
            ),

            "explanation": question.get(
                "explanation",
                ""
            ),

            "solution": question.get(
                "solution",
                ""
            ),

            "status": status

        })

    # =====================================================
    # PERCENTAGE
    # =====================================================

    percentage = round(

        (score / maximum_score) * 100,

        2

    ) if maximum_score else 0

    # =====================================================
    # AVERAGE QUESTION TIME
    # =====================================================

    average_time = round(

        sum(

            questions[question_index].get(
                "estimated_time",
                0
            )

            for question_index in question_order

        ) / total,

        2

    ) if total else 0

    # =====================================================
    # MOCK MODE
    # =====================================================

    current_mode = session.get(
        "mock_mode_" + exam_slug,
        "mixed"
    )

    if exam_slug == "gate":

        recommended_mode = next_difficulty_mode(
            percentage,
            current_mode
        )

    else:

        recommended_mode = current_mode

    # =====================================================
    # PROFESSIONAL MOCK TEST ANALYTICS
    # =====================================================

    attempted = correct + wrong

    accuracy = round(

        (correct / attempted) * 100,

        2

    ) if attempted else 0

    attempt_rate = round(

        (attempted / total) * 100,

        2

    ) if total else 0

    # =====================================================
    # PERFORMANCE LEVEL
    # =====================================================

    if percentage >= 85:

        performance_level = "Excellent"

        performance_message = (
            "Outstanding performance. "
            "You are ready for a higher-level challenge."
        )

    elif percentage >= 70:

        performance_level = "Strong"

        performance_message = (
            "Strong performance. "
            "Continue practicing difficult and mixed questions."
        )

    elif percentage >= 55:

        performance_level = "Good"

        performance_message = (
            "Good progress. "
            "Focus on improving accuracy and weak topics."
        )

    elif percentage >= 40:

        performance_level = "Needs Improvement"

        performance_message = (
            "Revise weak concepts and practice more questions "
            "before moving to advanced tests."
        )

    else:

        performance_level = "Beginner"

        performance_message = (
            "Build your fundamentals first and gradually "
            "increase question difficulty."
        )

    # =====================================================
    # STRONGEST / WEAKEST SUBJECT
    # =====================================================

    strongest_subject = "Not enough data"
    weakest_subject = "Not enough data"

    if subject_stats:

        subject_scores = []

        for name, data in subject_stats.items():

            subject_percentage = round(

                (
                    data["correct"]
                    /
                    data["total"]
                ) * 100,

                2

            ) if data["total"] else 0

            subject_scores.append(
                (
                    name,
                    subject_percentage
                )
            )

        subject_scores.sort(
            key=lambda x: x[1],
            reverse=True
        )

        if subject_scores:

            strongest_subject = subject_scores[0][0]

            weakest_subject = subject_scores[-1][0]

    # =====================================================
    # STRONGEST / WEAKEST TOPIC
    # =====================================================

    strongest_topic = "Not enough data"
    weakest_topic = "Not enough data"

    if topic_stats:

        topic_scores = []

        for name, data in topic_stats.items():

            topic_percentage = round(

                (
                    data["correct"]
                    /
                    data["total"]
                ) * 100,

                2

            ) if data["total"] else 0

            topic_scores.append(
                (
                    name,
                    topic_percentage
                )
            )

        topic_scores.sort(
            key=lambda x: x[1],
            reverse=True
        )

        if topic_scores:

            strongest_topic = topic_scores[0][0]

            weakest_topic = topic_scores[-1][0]

    # =====================================================
    # SMART RECOMMENDATION
    # =====================================================

    if percentage >= 85:

        smart_recommendation = (
            "You performed very well. "
            "Try a higher difficulty mock test "
            "and focus on maintaining accuracy "
            "under time pressure."
        )

    elif percentage >= 70:

        smart_recommendation = (
            f"Your performance is strong. "
            f"Revise {weakest_subject} "
            f"and practice more questions "
            f"from {weakest_topic}."
        )

    elif percentage >= 55:

        smart_recommendation = (
            f"Your fundamentals are developing. "
            f"Give extra attention to {weakest_subject} "
            f"and strengthen the topic {weakest_topic}."
        )

    else:

        smart_recommendation = (
            f"Focus on fundamentals before attempting "
            f"advanced tests. Start with {weakest_subject} "
            f"and revise {weakest_topic}."
        )

    # =====================================================
    # NEXT MOCK RECOMMENDATION
    # =====================================================

    if exam_slug == "gate":

        if percentage >= 85:

            next_test_recommendation = (
                "Advanced / L5–L7 Mock"
            )

        elif percentage >= 70:

            next_test_recommendation = (
                "Hard Mixed Mock"
            )

        elif percentage >= 55:

            next_test_recommendation = (
                "Moderate Mixed Mock"
            )

        else:

            next_test_recommendation = (
                "Foundation / L1–L3 Mock"
            )

    else:

        if percentage >= 75:

            next_test_recommendation = (
                "Higher Difficulty Mock"
            )

        elif percentage >= 50:

            next_test_recommendation = (
                "Standard Mixed Mock"
            )

        else:

            next_test_recommendation = (
                "Foundation Practice Mock"
            )

    # =====================================================
    # EXAM NAMES
    # =====================================================

    exam_names = {

        "gate": "GATE",

        "ssc-je": "SSC JE",

        "je-ae": "JE / AE",

        "diploma": "Diploma Civil",

        "btech": "B.Tech Civil",

        "government": "Government Exams"

    }

    exam_name = exam_names.get(

        exam_slug,

        exam_slug.replace(
            "-",
            " "
        ).upper()

    )

    # =====================================================
    # SAVE MOCK TEST RESULT
    # =====================================================

    saved_result_id = None
    attempt_id = session.get(
        "mock_attempt_" + exam_slug
    )

    if attempt_id:

        connection = get_db_connection()

        existing_result = connection.execute(
            """
            SELECT id FROM mock_test_results WHERE attempt_id = ?
            """,
            (attempt_id,)
        ).fetchone()

        if existing_result is None:

            connection.execute(

                """
                INSERT INTO mock_test_results
                (
                    student_id,
                    exam_slug,
                    exam_name,
                    total_questions,
                    correct,
                    wrong,
                    unanswered,
                    score,
                    percentage,
                    attempt_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,

                (
                    session["student_id"],

                    exam_slug,

                    exam_name,

                    total,

                    correct,

                    wrong,

                    unanswered,

                    score,

                    percentage,

                    attempt_id
                )

            )

            connection.commit()
            saved_result = connection.execute(
                "SELECT id FROM mock_test_results WHERE attempt_id = ?",
                (attempt_id,)
            ).fetchone()
            if saved_result:
                saved_result_id = saved_result["id"]
                connection.execute(
                    """
                    INSERT INTO mock_test_attempt_reviews
                        (result_id, student_id, review_json)
                    VALUES (?, ?, ?)
                    ON CONFLICT (result_id) DO NOTHING
                    """,
                    (saved_result["id"], session["student_id"], json.dumps(review))
                )
                connection.commit()

        else:
            existing_result = connection.execute(
                "SELECT id FROM mock_test_results WHERE attempt_id = ?",
                (attempt_id,)
            ).fetchone()
            if existing_result:
                saved_result_id = existing_result["id"]

            # Backfill/update exact review for a result saved by an earlier
            # version, only when no historical review row exists.
            connection.execute(
                """
                INSERT INTO mock_test_attempt_reviews (result_id, student_id, review_json)
                SELECT id, ?, ? FROM mock_test_results WHERE attempt_id = ?
                ON CONFLICT (result_id) DO NOTHING
                """,
                (session["student_id"], json.dumps(review), attempt_id)
            )
            connection.commit()

        connection.close()

        if saved_result_id:
            # Keep the saved result ID so refresh/back navigation cannot
            # accidentally regenerate this attempt's questions/results.
            session["mock_completed_result_id_" + exam_slug] = int(saved_result_id)

    # Feedback has been removed from the student mock-test workflow.
    session.pop("mock_feedback_pending_exam", None)

    # =====================================================
    # SHOW RESULT PAGE
    # =====================================================

    return render_template(

        "mock_result.html",

        student_name=session.get(
            "student_name",
            ""
        ),

        student_education=session.get(
            "student_education",
            ""
        ),

        student_email=session.get(
            "student_email",
            ""
        ),

        exam_name=exam_name,

        exam_slug=exam_slug,

        total=total,

        maximum_score=maximum_score,

        correct=correct,

        wrong=wrong,

        unanswered=unanswered,

        score=round(score, 2),

        percentage=percentage,

        review=review,

        feedback_submitted=feedback_submitted,

        average_time=average_time,

        subject_stats=subject_stats,

        topic_stats=topic_stats,

        difficulty_stats=difficulty_stats,

        current_mode=current_mode,

        recommended_mode=recommended_mode,

        attempted=attempted,

        accuracy=accuracy,

        attempt_rate=attempt_rate,

        performance_level=performance_level,

        performance_message=performance_message,

        strongest_subject=strongest_subject,

        weakest_subject=weakest_subject,

        strongest_topic=strongest_topic,

        weakest_topic=weakest_topic,

        smart_recommendation=smart_recommendation,

        next_test_recommendation=next_test_recommendation

    )



# =========================================================
# MOCK TEST RESULT PDF DOWNLOAD
# =========================================================
@app.route("/mock-test/<exam_slug>/result.pdf")
def mock_result_pdf(exam_slug):
    """Download the immutable saved result for the student's latest completed attempt."""
    if "student_id" not in session:
        return redirect(url_for("login"))
    if exam_slug not in MOCK_TEST_QUESTIONS:
        return "Mock test not available", 404

    connection = get_db_connection()
    try:
        result = connection.execute(
            """SELECT id
               FROM mock_test_results
               WHERE student_id=? AND exam_slug=?
               ORDER BY id DESC
               LIMIT 1""",
            (session["student_id"], exam_slug)
        ).fetchone()
    finally:
        connection.close()

    if result is None:
        return "No saved mock-test result is available for this attempt.", 404

    return redirect(url_for("download_mock_test_history", result_id=int(result["id"])))


# ==============================
# ERROR HANDLERS
# ==============================

@app.errorhandler(404)
def page_not_found(error):
    return render_template(
        "error.html",
        error_code=404,
        error_title="Page Not Found",
        error_message="The page you requested does not exist."
    ), 404


@app.errorhandler(500)
def internal_server_error(error):
    return render_template(
        "error.html",
        error_code=500,
        error_title="Something went wrong",
        error_message="The page could not be opened. Please return to the dashboard and try again."
    ), 500


# =========================================================
# SUBJECT MCQ
# =========================================================

@app.route(
    "/subject-practice/<subject_slug>",
    methods=["GET", "POST"]
)
def subject_mcq(subject_slug):

    if "student_id" not in session:
        return redirect(url_for("login"))

    if subject_slug not in SUBJECT_QUESTIONS:
        return "Subject not available", 404

    questions = SUBJECT_QUESTIONS[subject_slug]

    session_key_index = (
        "subject_index_" + subject_slug
    )

    session_key_score = (
        "subject_score_" + subject_slug
    )

    if session_key_index not in session:
        session[session_key_index] = 0

    if session_key_score not in session:
        session[session_key_score] = 0

    index = session[session_key_index]

    if index >= len(questions):

        index = 0

        session[session_key_index] = 0

        session[session_key_score] = 0

    question = questions[index]

    result = None

    if request.method == "POST":

        answer = request.form.get(
            "answer"
        )

        if answer == question["correct_answer"]:

            result = "Correct"

            session[session_key_score] += 1

        else:

            result = "Wrong"

    # =====================================================
    # SUBJECT NAMES
    # =====================================================

    subject_names = {

        "engineering-mathematics":
            "Engineering Mathematics",

        "strength-of-materials":
            "Strength of Materials",

        "concrete-technology":
            "Concrete Technology",

        "structural-engineering":
            "Structural Engineering",

        "geotechnical":
            "Geotechnical Engineering",

        "fluid-mechanics":
            "Fluid Mechanics",

        "transportation":
            "Transportation Engineering",

        "environmental":
            "Environmental Engineering",

        "surveying":
            "Surveying",

        "construction-materials":
            "Construction Materials",

        "construction-management":
            "Construction Management"

    }

    subject_name = subject_names.get(

        subject_slug,

        subject_slug.replace(
            "-",
            " "
        ).title()

    )

    return render_template(

        "subject_mcq.html",

        student_name=session.get(
            "student_name",
            ""
        ),

        student_education=session.get(
            "student_education",
            ""
        ),

        subject_name=subject_name,

        subject_slug=subject_slug,

        question=question,

        question_number=index + 1,

        total_questions=len(questions),

        score=session[session_key_score],

        result=result

    )


# =========================================================
# SUBJECT MCQ NEXT
# =========================================================

@app.route(
    "/subject-practice/<subject_slug>/next"
)
def subject_mcq_next(subject_slug):

    if "student_id" not in session:
        return redirect(url_for("login"))

    if subject_slug not in SUBJECT_QUESTIONS:
        return "Subject not available", 404

    session_key_index = (
        "subject_index_" + subject_slug
    )

    session_key_score = (
        "subject_score_" + subject_slug
    )

    if session_key_index not in session:
        session[session_key_index] = 0

    if session_key_score not in session:
        session[session_key_score] = 0

    session[session_key_index] += 1

    if session[session_key_index] >= len(
        SUBJECT_QUESTIONS[subject_slug]
    ):

        session[session_key_index] = 0

        session[session_key_score] = 0

    return redirect(

        url_for(
            "subject_mcq",
            subject_slug=subject_slug
        )

    )


# =========================================================
# FORGOT PASSWORD / PASSWORD RESET
# =========================================================

@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = str(request.form.get("email", "")).strip().lower()
        if not email:
            return render_template("forgot_password.html", error="Please enter your registered email address.")

        connection = get_db_connection()
        student = connection.execute("SELECT id, email FROM students WHERE lower(trim(email))=? LIMIT 1", (email,)).fetchone()
        if not student:
            connection.close()
            return render_template("forgot_password.html", message="If this email is registered, a password reset code has been sent.")

        code = str(secrets.randbelow(900000) + 100000)
        connection.execute("UPDATE students SET password_reset_code=?, password_reset_expires_at=? WHERE id=?", (code, _verification_expiry(), student["id"]))
        connection.commit()
        connection.close()

        try:
            sent = _send_verification_email(email, code, subject="Civil Career - Password Reset Code", purpose="password reset")
        except Exception as exc:
            print("[PASSWORD RESET EMAIL ERROR]", type(exc).__name__, exc, flush=True)
            sent = False
        if not sent:
            return render_template("forgot_password.html", error="Password reset email could not be sent. Please try again later.")
        return redirect(url_for("reset_password", email=email))

    return render_template("forgot_password.html")


@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    email = str(request.form.get("email", request.args.get("email", ""))).strip().lower()
    if request.method == "POST":
        code = str(request.form.get("code", "")).strip()
        password = str(request.form.get("password", ""))
        confirm_password = str(request.form.get("confirm_password", ""))
        if not email or not code or not password or not confirm_password:
            return render_template("reset_password.html", error="All fields are required.", email=email)
        if len(password) < 6:
            return render_template("reset_password.html", error="Password must be at least 6 characters.", email=email)
        if password != confirm_password:
            return render_template("reset_password.html", error="Passwords do not match.", email=email)

        connection = get_db_connection()
        student = connection.execute("SELECT id, password_reset_code, password_reset_expires_at FROM students WHERE lower(trim(email))=? LIMIT 1", (email,)).fetchone()
        if not student:
            connection.close()
            return render_template("reset_password.html", error="Invalid or expired reset request.", email=email)

        expires = student["password_reset_expires_at"]
        try:
            expired = not expires or datetime.fromisoformat(str(expires)) < datetime.utcnow()
        except ValueError:
            expired = True
        if expired or code != str(student["password_reset_code"] or ""):
            connection.close()
            return render_template("reset_password.html", error="Invalid or expired reset code.", email=email)

        connection.execute("UPDATE students SET password=?, password_reset_code=NULL, password_reset_expires_at=NULL WHERE id=?", (generate_password_hash(password), student["id"]))
        connection.commit()
        connection.close()
        return redirect(url_for("login"))

    return render_template("reset_password.html", email=email)

# =========================================================
# REGISTER
# =========================================================

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = str(request.form.get("name", "")).strip()
        email = str(request.form.get("email", "")).strip().lower()
        education = str(request.form.get("education", "")).strip()
        password = str(request.form.get("password", ""))
        confirm_password = str(request.form.get("confirm_password", ""))
        country_code = str(request.form.get("mobile_country_code", "")).strip()
        mobile = re.sub(r"\D", "", str(request.form.get("mobile_number", "")))

        if not all([name, email, education, password, confirm_password, country_code, mobile]):
            return render_template("register.html", error="All fields including country and mobile number are required.")
        if password != confirm_password:
            return render_template("register.html", error="Passwords do not match.")
        if len(mobile) < 7 or len(mobile) > 15:
            return render_template("register.html", error="Enter a valid mobile number.")

        connection = get_db_connection()
        try:
            connection.execute(
                """INSERT INTO students
                (name, email, education, password, user_id, mobile_country_code, mobile_number,
                 email_verified, mobile_verified, email_verification_code,
                 mobile_verification_code, verification_expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, NULL, NULL, NULL)""",
                (
                    name,
                    email,
                    education,
                    generate_password_hash(password),
                    _generate_user_id(connection, name),
                    country_code,
                    mobile,
                )
            )
            connection.commit()
        except psycopg_errors.UniqueViolation:
            connection.rollback()
            connection.close()
            return render_template("register.html", error="This email is already registered.")

        student = connection.execute(
            "SELECT * FROM students WHERE lower(trim(email))=? LIMIT 1",
            (email,)
        ).fetchone()
        connection.close()

        if not student:
            return render_template("register.html", error="Registration could not be completed. Please try again.")

        session["student_id"] = student["id"]
        session["last_activity"] = int(time.time())
        session.permanent = True
        session["student_name"] = student["name"]
        session["student_email"] = student["email"]
        session["student_education"] = student["education"]

        return redirect(url_for("profile", required=1))

    return render_template("register.html")



# =========================================================
# PROFILE ACCOUNT SETTINGS
# =========================================================

@app.route("/profile/change-password", methods=["POST"])
def profile_change_password():
    if "student_id" not in session:
        return redirect(url_for("login"))
    current = str(request.form.get("current_password", ""))
    new_password = str(request.form.get("new_password", ""))
    confirm = str(request.form.get("confirm_password", ""))

    connection = get_db_connection()
    student = connection.execute("SELECT password FROM students WHERE id=?", (session["student_id"],)).fetchone()

    valid = False
    try:
        valid = bool(student and check_password_hash(str(student["password"] or ""), current))
    except (ValueError, TypeError):
        valid = bool(student and str(student["password"] or "") == current)

    if not valid:
        connection.close()
        return redirect(url_for("profile", error="Current password is incorrect"))

    if len(new_password) < 6 or new_password != confirm:
        connection.close()
        return redirect(url_for("profile", error="New passwords must match and contain at least 6 characters"))

    connection.execute(
        "UPDATE students SET password=? WHERE id=?",
        (generate_password_hash(new_password), session["student_id"])
    )
    connection.commit()
    connection.close()
    return redirect(url_for("profile", message="Password changed successfully"))


@app.route("/profile/change-email", methods=["POST"])
def profile_change_email():
    if "student_id" not in session:
        return redirect(url_for("login"))

    new_email = str(request.form.get("new_email", "")).strip().lower()
    if not new_email:
        return redirect(url_for("profile", error="Enter a new email address"))

    connection = get_db_connection()
    current_student = connection.execute(
        "SELECT email FROM students WHERE id=?",
        (session["student_id"],)
    ).fetchone()
    current_email = str(current_student["email"] or "").strip().lower() if current_student else ""

    if new_email == current_email:
        connection.close()
        return redirect(url_for("profile", message="This is already your current email address."))

    existing = connection.execute(
        "SELECT id FROM students WHERE lower(trim(email))=? AND id<>?",
        (new_email, session["student_id"])
    ).fetchone()
    if existing:
        connection.close()
        return redirect(url_for("profile", error="That email address is already in use. Please use another email address."))

    connection.execute(
        "UPDATE students SET email=?, email_verified=1 WHERE id=?",
        (new_email, session["student_id"])
    )
    connection.commit()
    connection.close()

    session["student_email"] = new_email
    return redirect(url_for("profile", message="Email address changed successfully."))


@app.route("/profile/change-mobile", methods=["POST"])
def profile_change_mobile():
    if "student_id" not in session:
        return redirect(url_for("login"))

    country_code = str(request.form.get("mobile_country_code", "")).strip()
    mobile = re.sub(r"\D", "", str(request.form.get("mobile_number", "")))
    if not country_code or len(mobile) < 7 or len(mobile) > 15:
        return redirect(url_for("profile", error="Enter a valid country code and mobile number"))

    connection = get_db_connection()
    connection.execute(
        """UPDATE students
           SET mobile_country_code=?, mobile_number=?, mobile_verified=1
           WHERE id=?""",
        (country_code, mobile, session["student_id"])
    )
    connection.commit()
    connection.close()

    return redirect(url_for("profile", message="Mobile number changed successfully."))


# =========================================================
# REQUIRED MOCK-TEST FEEDBACK GUARD
# =========================================================

@app.before_request
def enforce_mock_feedback():
    """Feedback is optional/removed; never trap navigation on a result page."""
    session.pop("mock_feedback_pending_exam", None)
    return None


# =========================================================
# LOGOUT FEEDBACK
# =========================================================

@app.route("/logout-feedback", methods=["GET", "POST"])
def logout_feedback():
    """Legacy URL: feedback page removed; safely sign out instead."""
    session.clear()
    return redirect(url_for("login"))


# =========================================================
# LOGOUT
# =========================================================

@app.route("/auto-logout")
def auto_logout():
    session.clear()
    return redirect(url_for("login", expired=1))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))




@app.route("/jobs")
def jobs_hub():
    """Landing page for the three separate Civil Career job sections."""
    if "student_id" not in session:
        return redirect(url_for("login"))
    return render_template(
        "jobs.html",
        student_name=session.get("student_name", ""),
        student_education=session.get("student_education", "")
    )


@app.route("/non-government-jobs")
def non_government_jobs():
    """Show private-sector and non-government career paths for Civil Engineering qualifications."""
    if "student_id" not in session:
        return redirect(url_for("login"))
    return render_template(
        "non_government_jobs.html",
        student_name=session.get("student_name", ""),
        student_education=session.get("student_education", "")
    )


@app.route("/government-jobs/other")
def government_jobs_other():
    """Civil-eligible non-core and general government career paths."""
    if "student_id" not in session:
        return redirect(url_for("login"))

    filters = {key: request.args.get(key, "").strip() for key in ("search", "qualification", "status")}
    connection = get_db_connection()
    rows = connection.execute("""
        SELECT * FROM government_jobs
        WHERE notification_url != '' AND apply_url != '' AND source != ''
          AND vacancies != '' AND qualification != ''
          AND job_role_responsibilities != ''
          AND application_start IS NOT NULL AND application_start != ''
          AND application_last_datetime != ''
          AND (salary != '' OR pay_level != '')
          AND application_fee != ''
        ORDER BY application_last_datetime ASC, organization ASC
    """).fetchall()
    connection.close()

    # Show only notices whose titles/departments indicate non-core or general
    # government recruitment. Eligibility must still be checked in the official notice.
    non_core_terms = (
        "civil service", "ias", "ips", "ifs", "state psc", "appsc group", "tgpsc group",
        "group 1", "group-i", "group 2", "group-ii", "group 3", "group-iii",
        "group 4", "group-iv", "ssc cgl", "ssc chsl", "ssc cpo", "ssc mts",
        "ssc gd", "combined graduate", "combined higher secondary", "rrb ntpc",
        "rrb group d", "railway protection force", "railway recruitment",
        "administrative", "accounts", "audit", "bank", "insurance", "general duty",
        "general graduate", "graduate level", "steno", "clerical", "data entry",
        "assistant", "officer", "management trainee", "teaching", "lecturer",
        "faculty", "forest", "environment", "disaster management", "planning",
        "central government", "state government", "non technical", "non-technical"
    )
    jobs = []
    counts = {"NEW": 0, "OPEN": 0, "CLOSING SOON": 0, "EXAM DATE ANNOUNCED": 0, "CLOSED": 0}
    for row in rows:
        job = dict(row)
        haystack = " ".join(str(job.get(k) or "") for k in ("organization","post_name","department","job_type","branch")).lower()
        # Keep Civil technical engineering posts on the Core Civil page only.
        core_civil_markers = (
            "civil engineering", "junior engineer (civil)", "assistant engineer (civil)",
            "civil works", "civil branch", "civil discipline", "ssc je civil",
            "rrb je civil", "civil - structural", "civil – structural"
        )
        if any(term in haystack for term in core_civil_markers):
            continue
        if not any(term in haystack for term in non_core_terms):
            continue
        job["display_status"] = government_job_status(
            job.get("application_last_date"), job.get("exam_date"), job.get("status"),
            job.get("application_last_datetime")
        )
        if filters["search"] and filters["search"].lower() not in haystack:
            continue
        if filters["qualification"] and filters["qualification"].lower() not in str(job.get("qualification") or "").lower():
            continue
        if filters["status"] and filters["status"] != job["display_status"]:
            continue
        jobs.append(job)
        counts[job["display_status"]] = counts.get(job["display_status"], 0) + 1

    return render_template(
        "government_jobs_other.html",
        student_name=session.get("student_name", ""),
        student_education=session.get("student_education", ""),
        jobs=jobs, counts=counts, filters=filters
    )



# =========================================================
# SYLLABUS-ALIGNED SUBJECT LEARNING, QUIZ AND STUDY PDF
# =========================================================
SUBJECT_LEARNING = {
    "strength-of-materials": {
        "title": "Strength of Materials",
        "topics": [
            ("Simple stress and strain", "Normal stress = axial load / cross-sectional area. Normal strain = change in length / original length. Within the linear elastic range, Hooke's law gives σ = Eε.", "5-mark: A 20 kN tensile load acts on a 500 mm² bar. Find normal stress. Answer: σ = 20,000/500 = 40 N/mm² = 40 MPa."),
            ("Elastic constants", "Young's modulus E, shear modulus G and Poisson's ratio ν describe elastic response. For an isotropic, linear-elastic material: E = 2G(1+ν) and E = 3K(1−2ν).", "5-mark: If G = 80 GPa and ν = 0.25, E = 2×80×1.25 = 200 GPa."),
            ("Shear force and bending moment", "Shear force at a section is the algebraic sum of transverse forces on one side. Bending moment is the algebraic sum of moments about the section. For a simply supported beam with central point load P, maximum BM = PL/4.", "10-mark: A simply supported beam of span 6 m carries a central 20 kN point load. Reactions are 10 kN each; maximum BM = 20×6/4 = 30 kN·m at midspan."),
            ("Bending and torsion", "For elastic bending, M/I = σ/y = E/R. For a circular shaft in elastic torsion, T/J = τ/r = Gθ/L.", "5-mark: State the flexure formula and define M, I, σ, y, E and R.")
        ]
    },
    "concrete-technology": {
        "title": "Concrete Technology",
        "topics": [
            ("Cement and hydration", "Portland cement reacts with water (hydration) to form binding products. Heat evolution, setting and strength development depend on cement composition, fineness, temperature and curing.", "5-mark: Explain hydration and list two factors affecting strength development."),
            ("Fresh concrete and workability", "Workability is the ease of mixing, placing, compacting and finishing concrete without harmful segregation. Slump test is a field indicator of consistency; it is not a direct strength test.", "5-mark: Describe the slump test and state what its result indicates."),
            ("Water-cement ratio and strength", "For given materials and adequate compaction/curing, a lower water-cement ratio generally reduces capillary porosity and improves strength and durability. The required ratio must follow the approved mix design and exposure requirements.", "10-mark: Explain how water-cement ratio, compaction and curing influence concrete strength and durability."),
            ("Concrete testing and quality", "Fresh concrete tests include slump and workability checks. Hardened concrete compressive strength is commonly assessed using standard specimens and a calibrated compression testing machine, following the applicable IS standard and project specification.", "5-mark: Outline the steps in a concrete cube compressive-strength test and name the main reported measurement.")
        ]
    },
    "engineering-mathematics": {
        "title": "Engineering Mathematics",
        "topics": [
            ("Differential calculus", "For y=xⁿ, dy/dx=nxⁿ⁻¹. Derivatives represent rate of change and are used in maxima/minima, curve analysis and engineering models.", "5-mark: Differentiate y=3x³−4x²+2x−7. Answer: dy/dx=9x²−8x+2."),
            ("Integral calculus", "Integration is the inverse operation of differentiation (up to a constant). ∫xⁿdx=xⁿ⁺¹/(n+1)+C for n≠−1.", "5-mark: Evaluate ∫(2x+3)dx. Answer: x²+3x+C."),
            ("Matrices and linear systems", "A square matrix has equal rows and columns. For a nonsingular matrix A, the system Ax=b has the unique solution x=A⁻¹b.", "5-mark: State the condition for a square matrix to have an inverse: det(A)≠0."),
            ("Probability and statistics", "For mutually exclusive events, P(A∪B)=P(A)+P(B). For independent events, P(A∩B)=P(A)P(B).", "5-mark: If independent events have probabilities 0.4 and 0.5, their joint probability is 0.4×0.5=0.20.")
        ]
    }
}
LEARNING_QUESTIONS = {
    "strength-of-materials": [
        ("A 30 kN axial load acts on an area of 600 mm². Normal stress is:", ["25 MPa","50 MPa","180 MPa","500 MPa"], "B", "Stress = P/A = 30,000/600 = 50 N/mm² = 50 MPa."),
        ("Strain is:", ["Measured in N","Dimensionless","Measured in Pa","Measured in metres"], "B", "Strain is the ratio of change in length to original length, so units cancel."),
        ("A simply supported beam with a central point load P and span L has maximum BM:", ["PL/2","PL/4","PL/8","P/L"], "B", "The support reactions are P/2; maximum BM at midspan is (P/2)(L/2)=PL/4."),
        ("The SI unit of Young's modulus is:", ["N","N/m","Pa","J"], "C", "Young's modulus is stress divided by strain; strain is dimensionless, so the unit is Pa.")
    ],
    "concrete-technology": [
        ("The slump test is primarily an indicator of:", ["Compressive strength","Consistency/workability","Cement fineness","Aggregate impact value"], "B", "Slump indicates consistency/workability of fresh concrete; it does not directly measure strength."),
        ("The process of maintaining moisture and temperature for cement hydration is:", ["Curing","Segregation","Bleeding","Sieving"], "A", "Curing supports continued hydration and strength development."),
        ("The approximate specific gravity of ordinary Portland cement is:", ["1.0","2.0","3.15","4.5"], "C", "A commonly used approximate value is 3.15; use the value specified for the actual material."),
        ("For otherwise comparable concrete, excessive mixing water generally:", ["Always improves strength","Can increase porosity and reduce strength","Has no effect","Eliminates curing"], "B", "Excess water can leave capillary pores after hardening and reduce strength/durability.")
    ],
    "engineering-mathematics": [
        ("d(x³)/dx equals:", ["x²","2x","3x²","3x"], "C", "Apply the power rule: d(xⁿ)/dx=nxⁿ⁻¹."),
        ("∫2x dx equals:", ["2+C","x²+C","2x²+C","x+C"], "B", "The antiderivative of 2x is x² plus the constant of integration."),
        ("A matrix with the same number of rows and columns is:", ["Diagonal only","Square","Row matrix","Rectangular only"], "B", "A square matrix has equal row and column counts."),
        ("For independent events A and B, P(A∩B) is:", ["P(A)+P(B)","P(A)−P(B)","P(A)P(B)","P(A)/P(B)"], "C", "Independence means the joint probability is the product of the probabilities.")
    ]
}

@app.route("/learn/<subject_slug>")
def subject_learning(subject_slug):
    if "student_id" not in session:
        return redirect(url_for("login"))
    data = SUBJECT_LEARNING.get(subject_slug)
    questions = LEARNING_QUESTIONS.get(subject_slug, [])
    if not data:
        # Fall back to existing question bank, without inventing an unrelated subject.
        existing = SUBJECT_QUESTIONS.get(subject_slug, [])
        if not existing:
            return "Subject learning content is being prepared from its official syllabus.", 404
        data = {"title": subject_slug.replace("-", " ").title(), "topics": [
            ("Core concepts and revision", "Review the subject fundamentals and consult the applicable board/university syllabus for the prescribed unit sequence.", "5-mark: Define the principal terms in this subject and explain one engineering application.")
        ]}
        questions = [(q.get("question",""), [q.get("option_a",""),q.get("option_b",""),q.get("option_c",""),q.get("option_d","")],q.get("correct_answer","A"),"Review the related concept and verify against your prescribed textbook or standard.") for q in existing]
    count = request.args.get("count", default=5, type=int)
    count = max(5, min(count, 20))
    mode = request.args.get("mode", "quiz")
    if mode not in {"quiz","practice"}: mode="quiz"
    return render_template("subject_learning.html", student_name=session.get("student_name",""),
        student_education=session.get("student_education",""), subject_slug=subject_slug,
        learning=data, questions=questions[:count], question_count=min(count,len(questions)), mode=mode)

@app.route("/learn/<subject_slug>/notes.pdf")
def subject_notes_pdf(subject_slug):
    if "student_id" not in session:
        return redirect(url_for("login"))
    data=SUBJECT_LEARNING.get(subject_slug)
    if not data:
        return "Verified notes for this subject are not yet available.", 404
    buffer=BytesIO()
    doc=SimpleDocTemplate(buffer,pagesize=A4,rightMargin=18*mm,leftMargin=18*mm,topMargin=25*mm,bottomMargin=22*mm,title=data["title"]+" Study Notes",author="Civil Career")
    styles=getSampleStyleSheet()
    title=ParagraphStyle("CCLearnTitle",parent=styles["Title"],textColor=colors.HexColor("#12355B"),fontSize=23,leading=28,spaceAfter=10)
    heading=ParagraphStyle("CCLearnHeading",parent=styles["Heading2"],textColor=colors.HexColor("#12355B"),fontSize=14,leading=18,spaceBefore=14,spaceAfter=6)
    body=ParagraphStyle("CCLearnBody",parent=styles["BodyText"],fontSize=10,leading=15,spaceAfter=8,textColor=colors.HexColor("#334155"))
    story=[Paragraph("CIVIL CAREER",heading),Paragraph(escape(data["title"])+" — Study Notes",title),Paragraph("Subject-wise learning resource | Use with the current syllabus prescribed by your board, university or examination authority.",body),Spacer(1,8)]
    for topic,concept,example in data["topics"]:
        story += [Paragraph(escape(topic),heading),Paragraph(escape(concept),body),Paragraph("<b>Practice / solved example:</b> "+escape(example),body)]
    story += [Spacer(1,12),Paragraph("Academic note: These are original learning notes for revision. They are not a substitute for the current official syllabus, codes, standards or institution-issued study material. Verify applicable editions and specifications.",body)]
    def chrome(canvas, doc):
        draw_civilcareer_pdf_chrome(
            canvas, doc,
            header_right=data["title"] + " | Study Notes",
            footer_label=data["title"] + " Study Notes"
        )
    doc.build(story,onFirstPage=chrome,onLaterPages=chrome)
    buffer.seek(0)
    return send_file(buffer,mimetype="application/pdf",as_attachment=True,download_name=subject_slug+"-civil-career-notes.pdf")


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    create_database()

    app.run(
        debug=True
    )