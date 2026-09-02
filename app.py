import os
import sqlite3
import secrets
import io
import csv
import difflib
from datetime import datetime
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, 
    url_for, flash, session, jsonify, make_response, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

app = Flask(__name__)
app.secret_key = "meditrack_enterprise_super_secret_key_2026"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "meditrack.db")

DOCTOR_CATALOG = {
    "Dr. Sarah Smith": {"dept": "Cardiology", "avatar": "https://ui-avatars.com/api/?name=Sarah+Smith&background=0284c7&color=fff&size=150"},
    "Dr. Priya Sharma": {"dept": "General Medicine", "avatar": "https://ui-avatars.com/api/?name=Priya+Sharma&background=0f766e&color=fff&size=150"},
    "Dr. David Kim": {"dept": "Neurology", "avatar": "https://ui-avatars.com/api/?name=David+Kim&background=8b5cf6&color=fff&size=150"}
}

ALL_TIME_SLOTS = [
    "09:00 AM", "09:30 AM", "10:00 AM", "10:30 AM", 
    "11:00 AM", "11:30 AM", "02:00 PM", "02:30 PM", 
    "03:00 PM", "03:30 PM", "04:00 PM"
]

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Users & Staff Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT UNIQUE NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            age INTEGER NOT NULL,
            gender TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT NOT NULL,
            role TEXT DEFAULT 'patient',
            department TEXT,
            avatar_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Comprehensive EHR Profiles & Biometrics
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS patient_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            blood_group TEXT,
            height_cm REAL DEFAULT 0.0,
            weight_kg REAL DEFAULT 0.0,
            bmi REAL DEFAULT 0.0,
            allergies TEXT,
            existing_diseases TEXT,
            medical_history TEXT,
            emergency_contact TEXT,
            insurance_details TEXT,
            national_id_hash TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 3. Appointments Table with strict uniqueness
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_name TEXT NOT NULL,
            department TEXT NOT NULL,
            appointment_date TEXT NOT NULL,
            appointment_time TEXT NOT NULL,
            status TEXT DEFAULT 'Scheduled',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES users (id),
            UNIQUE(doctor_name, appointment_date, appointment_time)
        )
    ''')

    # 4. OPD Priority Queue Tokens
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS opd_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_number TEXT NOT NULL,
            patient_id INTEGER NOT NULL,
            department TEXT NOT NULL,
            priority_tier TEXT DEFAULT 'Regular', -- Emergency, Senior Citizen, Pregnant Woman, Child, Regular
            status TEXT DEFAULT 'WAITING',        -- WAITING, IN_CONSULT, COMPLETED, SKIPPED
            token_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES users (id)
        )
    ''')

    # 5. Clinical Consultations & Vitals Tracking
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            vitals_bp TEXT,
            vitals_pulse INTEGER,
            vitals_temp REAL,
            vitals_spo2 INTEGER,
            symptoms TEXT NOT NULL,
            diagnosis TEXT NOT NULL,
            treatment_plan TEXT NOT NULL,
            consultation_date TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES users (id),
            FOREIGN KEY (doctor_id) REFERENCES users (id)
        )
    ''')

    # 6. Prescriptions with Public Verification Codes
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rx_code TEXT UNIQUE NOT NULL,
            consultation_id INTEGER,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            medicine_name TEXT NOT NULL,
            dosage TEXT NOT NULL,
            duration TEXT NOT NULL,
            instructions TEXT,
            prescribed_date TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES users (id),
            FOREIGN KEY (doctor_id) REFERENCES users (id)
        )
    ''')

    # 7. Diagnostic Laboratory Test Desk
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lab_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            doctor_id INTEGER NOT NULL,
            test_type TEXT NOT NULL,
            parameter_name TEXT,
            parameter_value REAL,
            reference_range TEXT,
            result_flag TEXT DEFAULT 'PENDING', -- PENDING, NORMAL, HIGH, CRITICAL
            status TEXT DEFAULT 'ORDERED',       -- ORDERED, COMPLETED
            test_date TEXT NOT NULL,
            FOREIGN KEY (patient_id) REFERENCES users (id),
            FOREIGN KEY (doctor_id) REFERENCES users (id)
        )
    ''')

    # 8. Inpatient (IPD) Ward & Bed Management
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ipd_beds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ward_type TEXT NOT NULL,               -- General, ICU, Pediatric, Maternity
            bed_number TEXT UNIQUE NOT NULL,
            status TEXT DEFAULT 'AVAILABLE',      -- AVAILABLE, OCCUPIED, MAINTENANCE
            current_patient_id INTEGER,
            admitted_at TIMESTAMP,
            FOREIGN KEY (current_patient_id) REFERENCES users (id)
        )
    ''')

    # 9. Automated Hospital Billing & Tax Invoices
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS billing_invoices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_number TEXT UNIQUE NOT NULL,
            patient_id INTEGER NOT NULL,
            subtotal REAL NOT NULL,
            tax_gst REAL NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT DEFAULT 'Pending', -- Cash, UPI, Card, Insurance
            payment_status TEXT DEFAULT 'UNPAID',  -- UNPAID, PAID
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES users (id)
        )
    ''')

    # 10. Audit Logging Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            ip_address TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 11. API Keys Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            api_key TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # 12. Notifications
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            type TEXT DEFAULT 'normal',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')

    # Seed Master IPD Beds
    cursor.execute("SELECT COUNT(id) FROM ipd_beds")
    if cursor.fetchone()[0] == 0:
        wards = [("General", "GEN-101"), ("General", "GEN-102"), ("ICU", "ICU-01"), 
                 ("ICU", "ICU-02"), ("Pediatric", "PED-01"), ("Maternity", "MAT-01")]
        for w, b in wards:
            cursor.execute("INSERT INTO ipd_beds (ward_type, bed_number) VALUES (?, ?)", (w, b))

    # Seed Default Doctors
    for doc_name, data in DOCTOR_CATALOG.items():
        doc_email = f"{doc_name.split()[-1].lower()}@meditrack.com"
        cursor.execute("SELECT id FROM users WHERE email = ?", (doc_email,))
        if not cursor.fetchone():
            cursor.execute(
                """INSERT INTO users (patient_id, full_name, email, password, age, gender, phone, address, role, department, avatar_url)
                   VALUES (?, ?, ?, ?, 42, 'Physician', '9876500000', 'Medical Center', 'doctor', ?, ?)""",
                (f"DOC-{secrets.token_hex(2).upper()}", doc_name, doc_email, generate_password_hash("Doctor@123"), data["dept"], data["avatar"])
            )

    # Seed Receptionist
    cursor.execute("SELECT id FROM users WHERE email = 'reception@meditrack.com'")
    if not cursor.fetchone():
        cursor.execute(
            """INSERT INTO users (patient_id, full_name, email, password, age, gender, phone, address, role, avatar_url)
               VALUES ('REC-001', 'Reception Desk Staff', 'reception@meditrack.com', ?, 28, 'Staff', '9876500001', 'Floor 1', 'receptionist', 'https://ui-avatars.com/api/?name=Reception&background=64748b&color=fff&size=150')""",
            (generate_password_hash("Reception@123"),)
        )

    # Seed Admin
    cursor.execute("SELECT id FROM users WHERE email = 'admin@meditrack.com'")
    if not cursor.fetchone():
        cursor.execute(
            """INSERT INTO users (patient_id, full_name, email, password, age, gender, phone, address, role, avatar_url)
               VALUES ('ADM-001', 'Lead Administrator', 'admin@meditrack.com', ?, 35, 'Staff', '9876500002', 'HQ Tech Suite', 'admin', 'https://ui-avatars.com/api/?name=Admin&background=1e293b&color=fff&size=150')""",
            (generate_password_hash("Admin@123"),)
        )

    conn.commit()
    conn.close()

def log_audit(user_id, action, details=""):
    try:
        conn = get_db_connection()
        ip_addr = request.remote_addr if request else "127.0.0.1"
        conn.execute(
            "INSERT INTO audit_logs (user_id, action, details, ip_address) VALUES (?, ?, ?, ?)",
            (user_id, action, details, ip_addr)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def add_notification(user_id, title, message, notif_type="normal"):
    conn = get_db_connection()
    conn.execute(
        "INSERT INTO notifications (user_id, title, message, type) VALUES (?, ?, ?, ?)",
        (user_id, title, message, notif_type)
    )
    conn.commit()
    conn.close()

def generate_enterprise_patient_id():
    return f"MED-{secrets.token_hex(3).upper()}"

def check_fuzzy_duplicates(full_name, phone):
    conn = get_db_connection()
    existing_users = conn.execute("SELECT full_name, phone FROM users WHERE role = 'patient'").fetchall()
    conn.close()
    for u in existing_users:
        if u["phone"] == phone:
            return True
        ratio = difflib.SequenceMatcher(None, full_name.lower(), u["full_name"].lower()).ratio()
        if ratio > 0.88 and u["phone"][:6] == phone[:6]:
            return True
    return False

def evaluate_result_flag(test_type, val):
    try:
        v = float(val)
        if "Sugar" in test_type or "Glucose" in test_type:
            return "CRITICAL" if v > 200 else ("HIGH" if v > 140 else "NORMAL")
        if "Hemoglobin" in test_type:
            return "LOW" if v < 11.0 else "NORMAL"
        return "NORMAL"
    except Exception:
        return "NORMAL"

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if "user_id" not in session:
                flash("Session expired. Please sign in.", "warning")
                return redirect(url_for("login"))
            if session.get("user_role") not in allowed_roles:
                flash("Access Restricted: Unauthorized subsystem portal.", "danger")
                return redirect(url_for("dashboard_router"))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get("X-API-Key") or request.args.get("api_key")
        if not api_key:
            return jsonify({"status": "error", "message": "Missing X-API-Key header"}), 401
        conn = get_db_connection()
        record = conn.execute("SELECT * FROM api_keys WHERE api_key = ? AND is_active = 1", (api_key,)).fetchone()
        conn.close()
        if not record:
            return jsonify({"status": "error", "message": "Invalid API token"}), 403
        return f(*args, **kwargs)
    return decorated_function

@app.route("/dashboard")
def dashboard_router():
    if "user_id" not in session:
        return redirect(url_for("login"))
    role = session.get("user_role")
    if role == "doctor":
        return redirect(url_for("doctor_portal"))
    elif role == "receptionist":
        return redirect(url_for("receptionist_portal"))
    elif role == "admin":
        return redirect(url_for("admin_dashboard"))
    return redirect(url_for("profile"))

@app.route("/")
def index():
    return render_template("index.html", doctors=DOCTOR_CATALOG)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"].strip()
        email = request.form["email"].lower().strip()
        password = request.form["password"]
        age = int(request.form["age"])
        gender = request.form["gender"]
        phone = request.form["phone"].strip()
        address = request.form["address"].strip()

        if check_fuzzy_duplicates(full_name, phone):
            flash("Patient record conflict: A matching patient profile already exists.", "warning")
            return redirect(url_for("register"))

        hashed_password = generate_password_hash(password)
        patient_code = generate_enterprise_patient_id()
        avatar = f"https://ui-avatars.com/api/?name={full_name.replace(' ', '+')}&background=0284c7&color=fff&size=150"

        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """INSERT INTO users (patient_id, full_name, email, password, age, gender, phone, address, role, avatar_url) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'patient', ?)""",
                (patient_code, full_name, email, hashed_password, age, gender, phone, address, avatar)
            )
            new_id = cursor.lastrowid
            cursor.execute("INSERT INTO patient_profiles (user_id) VALUES (?)", (new_id,))
            conn.commit()

            add_notification(new_id, "Welcome to MediTrack", "Your verified patient identifier is ready.")
            log_audit(new_id, "REGISTER_PATIENT", f"Code {patient_code}")
            flash(f"Registration successful! Your official Patient Code is {patient_code}.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Email address is already in use.", "danger")
        finally:
            conn.close()

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].lower().strip()
        password = request.form["password"]

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["patient_id"] = user["patient_id"]
            session["user_name"] = user["full_name"]
            session["user_role"] = user["role"]
            session["avatar_url"] = user["avatar_url"]
            log_audit(user["id"], "AUTH_SUCCESS")
            flash(f"Welcome back, {user['full_name']}!", "success")
            return redirect(url_for("dashboard_router"))
        else:
            log_audit(None, "AUTH_FAILED", f"Email: {email}")
            flash("Invalid email or password.", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    if "user_id" in session:
        log_audit(session["user_id"], "AUTH_LOGOUT")
    session.clear()
    flash("Session cleared safely.", "info")
    return redirect(url_for("index"))

# --- REAL-TIME SLOT AVAILABILITY API ---
@app.route("/api/doctor-slots")
def get_available_slots():
    doctor_name = request.args.get("doctor_name")
    app_date = request.args.get("date")

    if not doctor_name or not app_date:
        return jsonify({"error": "Missing query parameters"}), 400

    conn = get_db_connection()
    booked = conn.execute(
        """SELECT appointment_time FROM appointments 
           WHERE doctor_name = ? AND appointment_date = ? AND status != 'Cancelled'""",
        (doctor_name, app_date)
    ).fetchall()
    conn.close()

    booked_times = [b["appointment_time"] for b in booked]
    availability = [
        {"time": slot, "available": slot not in booked_times}
        for slot in ALL_TIME_SLOTS
    ]
    return jsonify({"slots": availability, "department": DOCTOR_CATALOG.get(doctor_name, {}).get("dept", "Clinical Care")})

# --- APPOINTMENTS ENGINE ---
@app.route("/appointments", methods=["GET", "POST"])
@role_required(["patient"])
def appointments():
    conn = get_db_connection()
    user_id = session["user_id"]

    if request.method == "POST":
        doctor_name = request.form["doctor_name"]
        department = request.form["department"]
        app_date = request.form["appointment_date"]
        app_time = request.form["appointment_time"]

        try:
            conn.execute(
                """INSERT INTO appointments (patient_id, doctor_name, department, appointment_date, appointment_time) 
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, doctor_name, department, app_date, app_time)
            )
            conn.commit()
            add_notification(user_id, "Appointment Reserved", f"Booking confirmed with {doctor_name} on {app_date} at {app_time}")
            log_audit(user_id, "BOOK_APPOINTMENT", f"{doctor_name} @ {app_date} {app_time}")
            flash("Appointment successfully reserved with conflict-lock protection.", "success")
            return redirect(url_for("appointments"))
        except sqlite3.IntegrityError:
            flash("Conflict detected: That slot was just reserved by another patient.", "danger")

    user_appts = conn.execute(
        "SELECT * FROM appointments WHERE patient_id = ? ORDER BY appointment_date DESC", (user_id,)
    ).fetchall()
    conn.close()

    return render_template("appointments.html", appointments=user_appts, doctors=DOCTOR_CATALOG)

# --- EHR 360 PATIENT PORTAL ---
@app.route("/profile", methods=["GET", "POST"])
@role_required(["patient", "doctor", "receptionist", "admin"])
def profile():
    conn = get_db_connection()
    user_id = session["user_id"]

    if request.method == "POST" and "update_profile" in request.form:
        h = float(request.form.get("height_cm") or 0.0)
        w = float(request.form.get("weight_kg") or 0.0)
        bmi = round(w / ((h / 100) ** 2), 2) if h > 0 and w > 0 else 0.0

        conn.execute(
            """UPDATE patient_profiles 
               SET blood_group = ?, height_cm = ?, weight_kg = ?, bmi = ?, allergies = ?, 
                   existing_diseases = ?, medical_history = ?, emergency_contact = ?, insurance_details = ? 
               WHERE user_id = ?""",
            (request.form.get("blood_group"), h, w, bmi, request.form.get("allergies"),
             request.form.get("existing_diseases"), request.form.get("medical_history"),
             request.form.get("emergency_contact"), request.form.get("insurance_details"), user_id)
        )
        conn.commit()
        log_audit(user_id, "UPDATE_EHR_PROFILE")
        flash("EHR biometrics and clinical details synchronized.", "success")

    user_data = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    profile_data = conn.execute("SELECT * FROM patient_profiles WHERE user_id = ?", (user_id,)).fetchone()
    
    history = conn.execute(
        """SELECT c.*, u.full_name as doctor_name 
           FROM consultations c JOIN users u ON c.doctor_id = u.id 
           WHERE c.patient_id = ? ORDER BY c.consultation_date DESC""",
        (user_id,)
    ).fetchall()

    prescriptions = conn.execute(
        """SELECT p.*, u.full_name as doctor_name 
           FROM prescriptions p JOIN users u ON p.doctor_id = u.id 
           WHERE p.patient_id = ? ORDER BY p.prescribed_date DESC""",
        (user_id,)
    ).fetchall()

    lab_reports = conn.execute(
        "SELECT * FROM lab_tests WHERE patient_id = ? ORDER BY test_date DESC", (user_id,)
    ).fetchall()

    invoices = conn.execute(
        "SELECT * FROM billing_invoices WHERE patient_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall()

    my_appts = conn.execute(
        "SELECT * FROM appointments WHERE patient_id = ? ORDER BY appointment_date DESC", (user_id,)
    ).fetchall()

    conn.close()
    return render_template(
        "profile.html", 
        user=user_data, 
        profile=profile_data, 
        history=history, 
        prescriptions=prescriptions,
        lab_reports=lab_reports,
        invoices=invoices,
        appointments=my_appts
    )

# --- DOCTOR CLINICAL WORKSPACE ---
@app.route("/doctor/portal", methods=["GET", "POST"])
@role_required(["doctor"])
def doctor_portal():
    conn = get_db_connection()
    doctor_name = session["user_name"]
    doctor_id = session["user_id"]

    if request.method == "POST":
        patient_id = int(request.form["patient_user_id"])
        bp = request.form.get("vitals_bp", "120/80")
        pulse = int(request.form.get("vitals_pulse") or 72)
        temp = float(request.form.get("vitals_temp") or 98.6)
        spo2 = int(request.form.get("vitals_spo2") or 98)
        
        symptoms = request.form["symptoms"]
        diagnosis = request.form["diagnosis"]
        treatment_plan = request.form["treatment_plan"]
        today = datetime.now().strftime("%Y-%m-%d")

        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO consultations (patient_id, doctor_id, vitals_bp, vitals_pulse, vitals_temp, vitals_spo2, symptoms, diagnosis, treatment_plan, consultation_date) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, doctor_id, bp, pulse, temp, spo2, symptoms, diagnosis, treatment_plan, today)
        )
        consult_id = cursor.lastrowid

        # Digital prescription with public verification code
        rx_code = f"RX-{secrets.token_hex(4).upper()}"
        cursor.execute(
            """INSERT INTO prescriptions (rx_code, consultation_id, patient_id, doctor_id, medicine_name, dosage, duration, instructions, prescribed_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (rx_code, consult_id, patient_id, doctor_id, request.form["medicine_name"], 
             request.form["dosage"], request.form["duration"], request.form.get("instructions", ""), today)
        )

        # Generate Automated Bill
        inv_num = f"INV-2026-{secrets.token_hex(3).upper()}"
        cursor.execute(
            """INSERT INTO billing_invoices (invoice_number, patient_id, subtotal, tax_gst, total_amount, payment_status)
               VALUES (?, ?, 500.00, 90.00, 590.00, 'PAID')""",
            (inv_num, patient_id)
        )

        # Mark appointment as completed
        cursor.execute(
            "UPDATE appointments SET status = 'Completed' WHERE patient_id = ? AND doctor_name = ? AND status != 'Completed'",
            (patient_id, doctor_name)
        )
        conn.commit()

        add_notification(patient_id, "Prescription Issued", f"Clinical consultation summary #{rx_code} is ready.")
        log_audit(doctor_id, "FINALIZE_CONSULTATION", f"Patient #{patient_id}")
        flash("Consultation, vitals, digital prescription, and billing invoice finalized.", "success")
        return redirect(url_for("doctor_portal"))

    queue = conn.execute(
        """SELECT a.*, u.full_name as patient_name, u.age, u.gender, u.patient_id as patient_code, u.id as patient_user_id
           FROM appointments a JOIN users u ON a.patient_id = u.id 
           WHERE a.doctor_name = ? AND a.status != 'Completed'
           ORDER BY a.appointment_date ASC, a.appointment_time ASC""",
        (doctor_name,)
    ).fetchall()

    conn.close()
    return render_template("doctor_portal.html", queue=queue)

# --- RECEPTION DESK, OPD TOKENS & IPD BEDS ---
@app.route("/reception/portal", methods=["GET", "POST"])
@role_required(["receptionist", "admin"])
def receptionist_portal():
    conn = get_db_connection()

    if request.method == "POST":
        if "issue_token" in request.form:
            p_id = int(request.form["patient_user_id"])
            dept = request.form["department"]
            tier = request.form["priority_tier"]
            today = datetime.now().strftime("%Y-%m-%d")
            
            count = conn.execute("SELECT COUNT(id) FROM opd_tokens WHERE token_date = ?", (today,)).fetchone()[0]
            token_num = f"TK-{str(count + 1).zfill(3)}"

            conn.execute(
                "INSERT INTO opd_tokens (token_number, patient_id, department, priority_tier, token_date) VALUES (?, ?, ?, ?, ?)",
                (token_num, p_id, dept, tier, today)
            )
            conn.commit()
            log_audit(session["user_id"], "ISSUE_OPD_TOKEN", f"{token_num} ({tier})")
            flash(f"OPD Token {token_num} issued ({tier} priority).", "success")

        elif "admit_bed" in request.form:
            bed_id = int(request.form["bed_id"])
            p_id = int(request.form["patient_user_id"])
            conn.execute(
                "UPDATE ipd_beds SET status = 'OCCUPIED', current_patient_id = ?, admitted_at = CURRENT_TIMESTAMP WHERE id = ?",
                (p_id, bed_id)
            )
            conn.commit()
            flash("Inpatient allocated to ward bed.", "success")

        elif "discharge_bed" in request.form:
            bed_id = int(request.form["bed_id"])
            conn.execute(
                "UPDATE ipd_beds SET status = 'AVAILABLE', current_patient_id = NULL, admitted_at = NULL WHERE id = ?",
                (bed_id,)
            )
            conn.commit()
            flash("Bed released and marked available.", "info")

        return redirect(url_for("receptionist_portal"))

    today_str = datetime.now().strftime("%Y-%m-%d")
    tokens = conn.execute(
        """SELECT t.*, u.full_name as patient_name, u.patient_id as patient_code 
           FROM opd_tokens t JOIN users u ON t.patient_id = u.id 
           WHERE t.token_date = ? ORDER BY 
           CASE t.priority_tier 
             WHEN 'Emergency' THEN 1 
             WHEN 'Senior Citizen' THEN 2 
             WHEN 'Pregnant Woman' THEN 3 
             WHEN 'Child' THEN 4 
             ELSE 5 END ASC, t.id ASC""",
        (today_str,)
    ).fetchall()

    beds = conn.execute(
        """SELECT b.*, u.full_name as patient_name 
           FROM ipd_beds b LEFT JOIN users u ON b.current_patient_id = u.id"""
    ).fetchall()

    all_patients = conn.execute("SELECT id, full_name, patient_id FROM users WHERE role = 'patient'").fetchall()
    all_appts = conn.execute(
        """SELECT a.*, u.full_name as patient_name FROM appointments a JOIN users u ON a.patient_id = u.id 
           ORDER BY a.appointment_date DESC LIMIT 15"""
    ).fetchall()

    conn.close()
    return render_template(
        "receptionist_portal.html", 
        tokens=tokens, 
        beds=beds, 
        patients=all_patients, 
        appointments=all_appts
    )

# --- LIVE SMART QUEUE TV DISPLAY ---
@app.route("/queue/live")
def queue_live():
    return render_template("display_board.html")

@app.route("/queue/api/live_board")
def queue_api():
    conn = get_db_connection()
    today_str = datetime.now().strftime("%Y-%m-%d")
    tokens = conn.execute(
        """SELECT t.token_number, t.department, t.priority_tier, t.status, u.full_name as patient_name 
           FROM opd_tokens t JOIN users u ON t.patient_id = u.id 
           WHERE t.token_date = ? ORDER BY 
           CASE t.priority_tier 
             WHEN 'Emergency' THEN 1 
             WHEN 'Senior Citizen' THEN 2 
             WHEN 'Pregnant Woman' THEN 3 
             WHEN 'Child' THEN 4 
             ELSE 5 END ASC, t.id ASC LIMIT 8""",
        (today_str,)
    ).fetchall()
    conn.close()
    return jsonify({"tokens": [dict(r) for r in tokens]})

# --- PUBLIC AUTHENTICITY RX VERIFICATION ---
@app.route("/prescriptions/verify/<rx_code>")
def verify_prescription(rx_code):
    conn = get_db_connection()
    rx = conn.execute(
        """SELECT p.*, u.full_name as patient_name, u.patient_id as patient_code, 
                  d.full_name as doctor_name, d.department as doctor_dept
           FROM prescriptions p 
           JOIN users u ON p.patient_id = u.id 
           JOIN users d ON p.doctor_id = d.id 
           WHERE p.rx_code = ?""",
        (rx_code,)
    ).fetchone()
    conn.close()
    if not rx:
        return "<h2 style='color:red; text-align:center;'>❌ INVALID OR UNVERIFIED PRESCRIPTION CODE</h2>", 404
    return f"""
    <div style='font-family: sans-serif; max-width: 600px; margin: 40px auto; padding: 25px; border: 2px solid #0f766e; border-radius: 12px; background: #f0fdf4;'>
        <h2 style='color: #0f766e; margin-top: 0;'>✔ Verified Authentic Prescription</h2>
        <p><strong>Verification Code:</strong> {rx['rx_code']}</p>
        <p><strong>Patient:</strong> {rx['patient_name']} ({rx['patient_code']})</p>
        <p><strong>Doctor:</strong> {rx['doctor_name']} - {rx['doctor_dept']}</p>
        <p><strong>Prescribed Drug:</strong> {rx['medicine_name']} ({rx['dosage']})</p>
        <p><strong>Duration:</strong> {rx['duration']}</p>
        <p><strong>Official Date:</strong> {rx['prescribed_date']}</p>
        <hr style='border: 0; border-top: 1px solid #cbd5e1;'/>
        <small style='color: #64748b;'>Digitally verified against MediTrack Hospital Ledger.</small>
    </div>
    """

# --- EXECUTIVE ANALYTICS DASHBOARD ---
@app.route("/admin/dashboard")
@role_required(["admin"])
def admin_dashboard():
    conn = get_db_connection()
    stats = {
        "total_patients": conn.execute("SELECT COUNT(id) FROM users WHERE role = 'patient'").fetchone()[0],
        "total_appts": conn.execute("SELECT COUNT(id) FROM appointments").fetchone()[0],
        "completed_appts": conn.execute("SELECT COUNT(id) FROM appointments WHERE status = 'Completed'").fetchone()[0],
        "revenue": conn.execute("SELECT COALESCE(SUM(total_amount), 0) FROM billing_invoices").fetchone()[0],
        "occupied_beds": conn.execute("SELECT COUNT(id) FROM ipd_beds WHERE status = 'OCCUPIED'").fetchone()[0]
    }
    logs = conn.execute("SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 15").fetchall()
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, logs=logs)

# --- PDF GENERATOR ---
@app.route("/records/<int:consult_id>/pdf")
@role_required(["patient", "doctor", "admin"])
def download_prescription_pdf(consult_id):
    conn = get_db_connection()
    consult = conn.execute(
        """SELECT c.*, u.full_name as patient_name, u.patient_id as patient_code, 
                  doc.full_name as doctor_name, doc.department as doctor_dept
           FROM consultations c 
           JOIN users u ON c.patient_id = u.id 
           JOIN users doc ON c.doctor_id = doc.id 
           WHERE c.id = ?""",
        (consult_id,)
    ).fetchone()

    rx = conn.execute("SELECT * FROM prescriptions WHERE consultation_id = ?", (consult_id,)).fetchone()
    conn.close()

    if not consult:
        flash("Clinical record not found.", "danger")
        return redirect(url_for("profile"))

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    p.setTitle(f"Prescription_{consult['patient_code']}")

    p.setFont("Helvetica-Bold", 18)
    p.setFillColorRGB(0.01, 0.52, 0.78)
    p.drawString(50, 750, "MediTrack Healthcare Network")
    p.setFont("Helvetica", 10)
    p.setFillColorRGB(0.3, 0.3, 0.3)
    p.drawString(50, 735, f"Authenticated Clinical EHR Summary | Rx Code: {rx['rx_code'] if rx else 'N/A'}")
    p.line(50, 725, 560, 725)

    p.setFont("Helvetica-Bold", 10)
    p.setFillColorRGB(0, 0, 0)
    p.drawString(50, 695, f"PATIENT: {consult['patient_name']} ({consult['patient_code']})")
    p.drawString(340, 695, f"DATE: {consult['consultation_date']}")
    p.drawString(50, 675, f"ATTENDING PHYSICIAN: {consult['doctor_name']} ({consult['doctor_dept']})")

    # Vitals Block
    p.line(50, 660, 560, 660)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, 642, "Patient Vitals Recorded at Consultation:")
    p.setFont("Helvetica", 10)
    p.drawString(50, 625, f"• BP: {consult['vitals_bp']} mmHg")
    p.drawString(160, 625, f"• Pulse: {consult['vitals_pulse']} bpm")
    p.drawString(270, 625, f"• Temp: {consult['vitals_temp']} °F")
    p.drawString(380, 625, f"• SpO2: {consult['vitals_spo2']} %")

    # Clinical findings
    p.line(50, 610, 560, 610)
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, 590, "Clinical Findings & Diagnosis:")
    p.setFont("Helvetica", 10)
    p.drawString(70, 572, f"Symptoms: {consult['symptoms']}")
    p.drawString(70, 554, f"Confirmed Diagnosis: {consult['diagnosis']}")
    p.drawString(70, 536, f"Treatment Protocol: {consult['treatment_plan']}")

    # Prescription
    p.setFont("Helvetica-Bold", 11)
    p.drawString(50, 500, "Prescription (Rx):")
    p.setFont("Helvetica", 10)
    if rx:
        p.drawString(70, 482, f"Medication: {rx['medicine_name']} ({rx['dosage']})")
        p.drawString(70, 464, f"Duration: {rx['duration']}")
        p.drawString(70, 446, f"Instructions: {rx['instructions'] or 'Take as prescribed.'}")
    else:
        p.drawString(70, 482, "No pharmaceuticals prescribed.")

    p.setFont("Helvetica-Oblique", 8)
    p.setFillColorRGB(0.5, 0.5, 0.5)
    p.drawString(50, 60, f"Verify authenticity: http://127.0.0.1:8080/prescriptions/verify/{rx['rx_code'] if rx else ''}")
    p.showPage()
    p.save()

    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"EHR_{consult['patient_code']}_{consult_id}.pdf",
        mimetype="application/pdf"
    )

# --- CSV EXPORTS ---
@app.route("/admin/export/csv")
@role_required(["admin", "receptionist"])
def export_appointments_csv():
    conn = get_db_connection()
    appts = conn.execute(
        """SELECT a.id, u.patient_id, u.full_name, a.doctor_name, a.department, a.appointment_date, a.appointment_time, a.status 
           FROM appointments a JOIN users u ON a.patient_id = u.id"""
    ).fetchall()
    conn.close()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["ID", "Patient Code", "Name", "Doctor", "Department", "Date", "Time", "Status"])
    for r in appts:
        cw.writerow(list(r))

    response = make_response(si.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=meditrack_appts.csv"
    response.headers["Content-type"] = "text/csv"
    return response

# --- DEVELOPER API KEYS & REST APIS ---
@app.route("/api/keys", methods=["GET", "POST"])
@role_required(["doctor", "admin", "receptionist"])
def api_key_management():
    conn = get_db_connection()
    user_id = session["user_id"]

    if request.method == "POST":
        if "generate_key" in request.form:
            label = request.form["label"].strip() or "Client App"
            new_key = f"mtk_live_{secrets.token_hex(16)}"
            conn.execute("INSERT INTO api_keys (user_id, api_key, label) VALUES (?, ?, ?)", (user_id, new_key, label))
            conn.commit()
            log_audit(user_id, "CREATE_API_KEY", f"Label: {label}")
            flash("New API Key generated successfully!", "success")
        elif "revoke_key" in request.form:
            key_id = request.form["key_id"]
            conn.execute("UPDATE api_keys SET is_active = 0 WHERE id = ? AND user_id = ?", (key_id, user_id))
            conn.commit()
            flash("API Key revoked.", "info")
        return redirect(url_for("api_key_management"))

    keys = conn.execute("SELECT * FROM api_keys WHERE user_id = ? ORDER BY created_at DESC", (user_id,)).fetchall()
    conn.close()
    return render_template("api_keys.html", keys=keys)

@app.route("/api/v1/patients", methods=["GET"])
@require_api_key
def api_get_patients():
    conn = get_db_connection()
    patients = conn.execute(
        """SELECT u.id, u.patient_id, u.full_name, u.email, u.age, u.gender, u.phone, 
                  p.blood_group, p.bmi, p.allergies, p.existing_diseases 
           FROM users u LEFT JOIN patient_profiles p ON u.id = p.user_id 
           WHERE u.role = 'patient'"""
    ).fetchall()
    conn.close()
    return jsonify({"status": "success", "count": len(patients), "data": [dict(row) for row in patients]}), 200

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=8080)