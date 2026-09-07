from flask import Flask, render_template, request, redirect, url_for, session, send_file
import json
import time
import sqlite3
import uuid
import random
import os
from datetime import date, datetime, timedelta
from io import BytesIO
from html import escape
from werkzeug.utils import secure_filename
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable
from gate_mock_engine import GATE_SYLLABI, GATE_SYLLABUS, build_gate_mock, next_difficulty_mode

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["PROFILE_UPLOAD_FOLDER"] = os.path.join(
    app.root_path, "static", "images", "profile_uploads"
)

# Secret key for login sessions
# This is fine for our local development project.
app.secret_key = "civil-career-development-key"


# ==============================
# DATABASE CONNECTION
# ==============================

def get_db_connection():

    connection = sqlite3.connect("civilcareer.db")

    connection.row_factory = sqlite3.Row

    return connection


# ==============================
# CREATE DATABASE
# ==============================

def create_database():

    connection = get_db_connection()


    # ==========================================
    # STUDENTS TABLE
    # ==========================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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


    # ==========================================
    # MOCK TEST HISTORY TABLE
    # ==========================================

    connection.execute("""
        CREATE TABLE IF NOT EXISTS mock_test_results (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            exam_date TEXT,
            application_fee TEXT NOT NULL DEFAULT '',
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

    connection.execute("""
        CREATE TABLE IF NOT EXISTS user_job_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            job_id INTEGER NOT NULL,
            notification_type TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, job_id, notification_type)
        )
    """)


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


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form["email"]

        password = request.form["password"]

        connection = get_db_connection()

        student = connection.execute(
            """
            SELECT *
            FROM students
            WHERE email = ? AND password = ?
            """,
            (email, password)
        ).fetchone()

        connection.close()

        # LOGIN SUCCESS
        if student:

            # Store student information in session
            session["student_id"] = student["id"]
            session["student_name"] = student["name"]
            session["student_email"] = student["email"]
            session["student_education"] = student["education"]

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
    verified_jobs = connection.execute(
        """
        SELECT application_last_date, exam_date, status
        FROM government_jobs
        WHERE notification_url != '' AND apply_url != '' AND source != ''
        """
    ).fetchall()
    connection.close()
    job_counts = {"NEW": 0, "OPEN": 0, "CLOSING SOON": 0}
    for job in verified_jobs:
        status = government_job_status(
            job["application_last_date"], job["exam_date"], job["status"]
        )
        if status in job_counts:
            job_counts[status] += 1

    matching_jobs = get_matching_jobs(session["student_id"], limit=3)

    return render_template(

        "dashboard.html",

        student_name=student_name,

        student_education=student_education,
        job_counts=job_counts,
        matching_jobs=matching_jobs,

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

    syllabus_year = request.args.get("year", "2026")
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

def government_job_status(last_date, exam_date, stored_status):
    if stored_status in {"RESULT", "ADMIT CARD", "CANCELLED"}:
        return stored_status
    today = date.today()
    try:
        if last_date:
            closing = datetime.strptime(last_date, "%Y-%m-%d").date()
            if closing < today:
                return "CLOSED"
            if closing <= today + timedelta(days=7):
                return "CLOSING SOON"
        if exam_date:
            exam = datetime.strptime(exam_date, "%Y-%m-%d").date()
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
    checks = 0

    qualification_pref = (preferences.get("qualification") or "").strip()
    if qualification_pref:
        checks += 1
        job_qualification = (job.get("qualification") or "").lower()
        if qualification_pref.lower() in job_qualification or any(
            item.lower() in job_qualification for item in qualification_pref.split("/")
        ):
            score += 35
        elif any(item.lower() in job_qualification for item in ["diploma", "b.tech", "b.e.", "m.tech", "civil"]):
            score += 20

    branch_pref = (preferences.get("branch") or "").strip()
    if branch_pref:
        checks += 1
        job_branch = (job.get("branch") or job.get("qualification") or "").lower()
        if "civil" in branch_pref.lower() and "civil" in job_branch:
            score += 25
        else:
            score += 10

    states = _normalize_list(preferences.get("preferred_states"))
    if states:
        checks += 1
        job_location = (job.get("job_location") or "").lower()
        if any(state.lower() in job_location for state in states):
            score += 15
        else:
            score += 5

    preferred_job_types = _normalize_list(preferences.get("job_types"))
    if preferred_job_types:
        checks += 1
        job_type = (job.get("job_type") or "").lower()
        if any(job_type == item.lower() or item.lower() in job_type for item in preferred_job_types):
            score += 15
        else:
            score += 5

    experience = (preferences.get("experience") or "").lower()
    if experience:
        checks += 1
        if "fresher" in experience and ("fresher" in job.get("qualification", "").lower() or "0" in (job.get("age_limit") or "")):
            score += 10
        else:
            score += 5

    if checks == 0:
        return 50

    return min(100, max(0, int(round(score / checks * 100 / 100))))


def get_matching_jobs(student_id, limit=3):
    preferences = get_user_job_preferences(student_id)
    connection = get_db_connection()
    rows = connection.execute(
        """
        SELECT * FROM government_jobs
        WHERE notification_url != '' AND apply_url != '' AND source != ''
        ORDER BY application_last_date IS NULL, application_last_date ASC
        """
    ).fetchall()
    connection.close()

    matches = []
    for row in rows:
        job = dict(row)
        job["display_status"] = government_job_status(
            job["application_last_date"], job["exam_date"], job["status"]
        )
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
        """, (job_id,)
    ).fetchone()
    connection.close()
    if not job:
        return "Government job not available", 404
    job = dict(job)
    job["display_status"] = government_job_status(
        job["application_last_date"], job["exam_date"], job["status"]
    )
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
        ORDER BY application_last_date IS NULL, application_last_date ASC
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

    syllabus_year = request.args.get("year", "2026")
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
        canvas.setStrokeColor(colors.HexColor("#D9E2EC"))
        canvas.setLineWidth(0.6)
        canvas.line(18 * mm, height - 17 * mm, width - 18 * mm, height - 17 * mm)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(colors.HexColor("#12355B"))
        canvas.drawString(18 * mm, height - 12 * mm, "CIVIL CAREER")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748B"))
        canvas.drawRightString(width - 18 * mm, height - 12 * mm, "GATE " + year + " | Civil Engineering")
        canvas.line(18 * mm, 13 * mm, width - 18 * mm, 13 * mm)
        canvas.drawString(18 * mm, 8 * mm, "Civil Career | Official syllabus reference")
        canvas.drawRightString(width - 18 * mm, 8 * mm, "Page " + str(canvas.getPageNumber()))
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
        Paragraph("Use this document as the syllabus boundary for Civil Career preparation and mock tests.", small_style),
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

    return render_template(
        "notifications.html",
        student_name=session["student_name"],
        student_education=session["student_education"]
    )


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

@app.route("/profile", methods=["GET", "POST"])
def profile():

    if "student_id" not in session:
        return redirect(url_for("login"))

    connection = get_db_connection()
    profile_error = None
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "personal":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            education = request.form.get("education", "").strip()
            if not name or not email or not education:
                profile_error = "Name, email, and education are required."
            else:
                try:
                    connection.execute(
                        "UPDATE students SET name = ?, email = ?, education = ? WHERE id = ?",
                        (name, email, education, session["student_id"])
                    )
                    connection.commit()
                    session["student_name"] = name
                    session["student_email"] = email
                    session["student_education"] = education
                except sqlite3.IntegrityError:
                    profile_error = "That email address is already in use."

        elif action == "photo":
            photo = request.files.get("profile_photo")
            allowed_extensions = {"jpg", "jpeg", "png", "webp"}
            extension = os.path.splitext(photo.filename or "")[1].lower().lstrip(".") if photo else ""
            if not photo or not photo.filename:
                profile_error = "Choose an image to upload."
            elif extension not in allowed_extensions:
                profile_error = "Use a JPG, PNG, or WEBP image."
            else:
                os.makedirs(app.config["PROFILE_UPLOAD_FOLDER"], exist_ok=True)
                filename = secure_filename(
                    "student-" + str(session["student_id"]) + "-" + uuid.uuid4().hex + "." + extension
                )
                photo.save(os.path.join(app.config["PROFILE_UPLOAD_FOLDER"], filename))
                connection.execute(
                    "UPDATE students SET profile_photo = ? WHERE id = ?",
                    (filename, session["student_id"])
                )
                connection.commit()

        elif action == "target":
            target_exam = request.form.get("target_exam", "").strip()
            allowed_exams = {
                "GATE Civil Engineering", "SSC JE", "JE / AE",
                "Diploma Civil", "B.Tech Civil", "Government Exams"
            }
            if target_exam in allowed_exams:
                connection.execute(
                    """
                    INSERT INTO student_preferences (student_id, target_exam)
                    VALUES (?, ?)
                    ON CONFLICT(student_id) DO UPDATE SET
                        target_exam = excluded.target_exam,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (session["student_id"], target_exam)
                )
                connection.commit()

    student = connection.execute(
        "SELECT name, email, education, profile_photo FROM students WHERE id = ?",
        (session["student_id"],)
    ).fetchone()

    preference = connection.execute(
        "SELECT target_exam FROM student_preferences WHERE student_id = ?",
        (session["student_id"],)
    ).fetchone()
    score_summary = connection.execute(
        """
        SELECT COUNT(*) AS tests_taken,
               COALESCE(ROUND(AVG(percentage), 1), 0) AS average_score,
               COALESCE(MAX(percentage), 0) AS best_score
        FROM mock_test_results
        WHERE student_id = ?
        """,
        (session["student_id"],)
    ).fetchone()
    recent_results = connection.execute(
        """
        SELECT id, exam_name, score, percentage, created_at
        FROM mock_test_results
        WHERE student_id = ?
        ORDER BY id DESC LIMIT 5
        """,
        (session["student_id"],)
    ).fetchall()
    connection.close()

    return render_template(
        "profile.html",
        student_name=session["student_name"],
        student_education=session["student_education"],
        student_email=student["email"] if student else session.get("student_email", ""),
        target_exam=preference["target_exam"] if preference else "GATE Civil Engineering",
        profile_photo=student["profile_photo"] if student else None,
        profile_error=profile_error,
        tests_taken=score_summary["tests_taken"],
        average_score=score_summary["average_score"],
        best_score=score_summary["best_score"],
        exam_progress=min(100, round(score_summary["average_score"])),
        practice_progress=min(100, score_summary["tests_taken"] * 10),
        recent_results=recent_results
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

MOCK_TEST_DURATION_SECONDS = 180 * 60


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

    mode_key = "mock_mode_" + exam_slug
    profile_key = "mock_profile_" + exam_slug
    scope_key = "mock_scope_" + exam_slug
    count_key = "mock_count_" + exam_slug


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

    start_new = request.args.get("new") == "1"


    # ==========================================
    # LOAD QUESTIONS
    # ==========================================

    if exam_slug == "gate":

        if (
            start_new
            or mode_key not in session
        ):

            session[mode_key] = requested_mode
            session[profile_key] = requested_profile
            session[scope_key] = requested_scope
            session[count_key] = requested_count


        questions = build_gate_mock(

            session.get(
                mode_key,
                "mixed"
            ),

            count=session.get(
                count_key,
                0
            ) or 20,

            profile=(
                session.get(
                    profile_key,
                    "full"
                )
                if session.get(
                    scope_key,
                    "all"
                ) == "all"
                else None
            ),

            scope=session.get(
                scope_key,
                "all"
            )
        )

    else:

        questions = MOCK_TEST_QUESTIONS[exam_slug]


    # ==========================================
    # NEW ATTEMPT
    # ==========================================

    if (
        start_new
        or timer_key not in session
        or order_key not in session
        or answers_key not in session
    ):

        # --------------------------------------
        # TIMER = 180 MINUTES
        # --------------------------------------

        session[timer_key] = (
            int(time.time())
            + MOCK_TEST_DURATION_SECONDS
        )


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

                session[index_key] = (
                    current_index - 1
                )


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

            status = "current"

        elif number in session.get(
            doubt_key,
            []
        ):

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
            if status == "review"
        ]

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

    questions = build_gate_mock(
        session.get("mock_mode_" + exam_slug, "mixed"),
        count=session.get("mock_count_" + exam_slug, 0) or 20,
        profile=session.get("mock_profile_" + exam_slug, "full") if session.get("mock_scope_" + exam_slug, "all") == "all" else None,
        scope=session.get("mock_scope_" + exam_slug, "all")
    ) if exam_slug == "gate" else MOCK_TEST_QUESTIONS[exam_slug]

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

    # =====================================================
    # LOAD QUESTIONS
    # =====================================================

    if exam_slug == "gate":

        questions = build_gate_mock(

            session.get(
                "mock_mode_" + exam_slug,
                "mixed"
            ),

            count=session.get(
                "mock_count_" + exam_slug,
                0
            ) or 20,

            profile=(
                session.get(
                    "mock_profile_" + exam_slug,
                    "full"
                )
                if session.get(
                    "mock_scope_" + exam_slug,
                    "all"
                ) == "all"
                else None
            ),

            scope=session.get(
                "mock_scope_" + exam_slug,
                "all"
            )
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

    attempt_id = session.get(
        "mock_attempt_" + exam_slug
    )

    if attempt_id:

        connection = get_db_connection()

        existing_result = connection.execute(

            """
            SELECT id
            FROM mock_test_results
            WHERE attempt_id = ?
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

        connection.close()

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

        score=score,

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
# REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        name = request.form["name"]

        email = request.form["email"]

        education = request.form["education"]

        password = request.form["password"]

        confirm_password = request.form[
            "confirm_password"
        ]

        # =================================================
        # CHECK PASSWORD
        # =================================================

        if password != confirm_password:

            return render_template(

                "register.html",

                error="Passwords do not match."

            )

        connection = get_db_connection()

        try:

            connection.execute(

                """
                INSERT INTO students
                (
                    name,
                    email,
                    education,
                    password
                )
                VALUES (?, ?, ?, ?)
                """,

                (
                    name,
                    email,
                    education,
                    password
                )

            )

            connection.commit()

        except sqlite3.IntegrityError:

            connection.close()

            return render_template(

                "register.html",

                error=(
                    "This email is already registered."
                )

            )

        connection.close()

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )


# =========================================================
# START APPLICATION
# =========================================================

if __name__ == "__main__":

    create_database()

    app.run(
        debug=True
    )