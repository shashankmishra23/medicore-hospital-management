"""
Patient portal: patients sign up, book appointments online and see
their own prescriptions and bills. A patient can only ever see their own data.
"""
from datetime import date, timedelta

from flask import Blueprint, abort, current_app, jsonify, request, session
from werkzeug.security import generate_password_hash

from audit import audit
from auth import current_patient, verify_password
from db import query, query_one, transaction
from routes.appointments import book, check_doctor_works, free_slots, get_doctor, parse_time
from routes.patients import BLOOD_GROUPS, GENDERS
from utils import (as_choice, as_date, check_email, check_password_strength,
                   check_phone, clean, get_json, require)

bp = Blueprint("portal", __name__, url_prefix="/api/portal")

BOOK_DAYS_AHEAD = 30


def me_id():
    return current_patient()["patient_id"]


def start_session(account):
    session.clear()
    session.permanent = True
    session["patient"] = {
        "account_id": account["account_id"],
        "patient_id": account["patient_id"],
        "name": f"{account['first_name']} {account['last_name']}",
        "email": account["email"],
        "must_change_password": bool(account.get("must_change_password")) and not current_app.config["DEMO_MODE"],
    }


# Sign up / sign in
@bp.route("/register", methods=["POST"])
def register():
    data = get_json()
    require(data, "first_name", "last_name", "dob", "gender", "phone", "email", "password")
    email = check_email(data["email"]).lower()
    phone = check_phone(data["phone"])
    dob = as_date(data["dob"], "Date of birth")
    if dob >= date.today():
        abort(400, "Date of birth must be in the past.")
    check_password_strength(data["password"])
    if query_one("SELECT 1 FROM patient_accounts WHERE email=%s", (email,)):
        abort(409, "An account with this email already exists. Please sign in.")

    # Sign-up always makes a new record. Patients who already have a hospital
    # record get portal access from reception after showing ID, so nobody can
    # open someone else's records just by knowing their phone and birthday.
    with transaction() as cur:
        cur.execute("""
            INSERT INTO patients (first_name, last_name, dob, gender, phone, email)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (clean(data["first_name"]), clean(data["last_name"]), dob,
              as_choice(data["gender"], "Gender", GENDERS), phone, email))
        patient_id = cur.lastrowid
        cur.execute("""
            INSERT INTO patient_accounts (patient_id, email, password_hash) VALUES (%s,%s,%s)
        """, (patient_id, email, generate_password_hash(data["password"])))
        account_id = cur.lastrowid

    start_session({"account_id": account_id, "patient_id": patient_id, "email": email,
                   "first_name": clean(data["first_name"]), "last_name": clean(data["last_name"])})
    audit("Registered online", f"P-{patient_id:03d}")
    return jsonify({"success": True, "patient_id": patient_id}), 201


@bp.route("/login", methods=["POST"])
def login():
    data = get_json()
    require(data, "email", "password")
    account = query_one("""
        SELECT a.*, p.first_name, p.last_name
        FROM patient_accounts a JOIN patients p ON p.patient_id=a.patient_id
        WHERE a.email=%s
    """, (data["email"].strip().lower(),))
    if not account:
        abort(401, "Wrong email or password.")
    verify_password("patient_accounts", "account_id", account, data["password"])
    if not account["is_active"]:
        abort(403, "This account has been turned off. Please call the hospital.")
    start_session(account)
    audit("Signed in")
    return jsonify({"success": True})


# My details
@bp.route("/me", methods=["GET"])
def me():
    pid = me_id()
    patient = query_one("""
        SELECT p.*, a.email AS login_email FROM patients p
        JOIN patient_accounts a ON a.patient_id=p.patient_id
        WHERE p.patient_id=%s
    """, (pid,))
    patient["upcoming"] = query("""
        SELECT a.appointment_id, a.appointment_date, a.appointment_time, a.reason, a.status,
               CONCAT('Dr. ', s.first_name,' ',s.last_name) AS doctor_name, d.specialization
        FROM appointments a
        JOIN doctors d ON d.doctor_id=a.doctor_id
        JOIN staff s ON s.staff_id=d.staff_id
        WHERE a.patient_id=%s AND a.status='Scheduled' AND a.appointment_date >= CURDATE()
        ORDER BY a.appointment_date, a.appointment_time
    """, (pid,))
    patient["unpaid_total"] = query_one("""
        SELECT COALESCE(SUM(balance),0) AS n FROM bills
        WHERE patient_id=%s AND status IN ('Pending','Partial')
    """, (pid,))["n"]
    patient["prescription_count"] = query_one(
        "SELECT COUNT(*) AS n FROM prescriptions WHERE patient_id=%s", (pid,))["n"]
    patient["admitted"] = query_one("""
        SELECT a.admission_date, r.room_number, w.ward_name FROM patient_admissions a
        LEFT JOIN rooms r ON r.room_id=a.room_id LEFT JOIN wards w ON w.ward_id=r.ward_id
        WHERE a.patient_id=%s AND a.status='Admitted'
    """, (pid,))
    patient["must_change_password"] = current_patient().get("must_change_password", False)
    return jsonify(patient)


@bp.route("/profile", methods=["PUT"])
def update_profile():
    """Patients can keep their contact details and allergies up to date."""
    data = get_json()
    require(data, "phone")
    blood = clean(data.get("blood_group"))
    with transaction() as cur:
        cur.execute("""
            UPDATE patients SET phone=%s, address=%s, blood_group=%s,
                   emergency_contact_name=%s, emergency_contact_phone=%s, allergies=%s
            WHERE patient_id=%s
        """, (check_phone(data["phone"]), clean(data.get("address")),
              as_choice(blood, "Blood group", BLOOD_GROUPS) if blood else None,
              clean(data.get("emergency_contact_name")),
              check_phone(data.get("emergency_contact_phone"), "Emergency contact phone"),
              clean(data.get("allergies")), me_id()))
    audit("Updated own profile")
    return jsonify({"success": True})


# Booking
@bp.route("/doctors", methods=["GET"])
def doctors():
    return jsonify(query("""
        SELECT d.doctor_id, d.specialization, d.qualification, d.consultation_fee, d.available_days,
               CONCAT('Dr. ', s.first_name,' ',s.last_name) AS name, s.gender, dep.dept_name
        FROM doctors d
        JOIN staff s ON s.staff_id=d.staff_id
        LEFT JOIN departments dep ON dep.dept_id=s.dept_id
        WHERE s.status='Active'
        ORDER BY d.specialization, s.first_name
    """))


def check_booking_date(day):
    if day < date.today():
        abort(400, "Please choose today or a later date.")
    if day > date.today() + timedelta(days=BOOK_DAYS_AHEAD):
        abort(400, f"Appointments can be booked up to {BOOK_DAYS_AHEAD} days ahead.")


@bp.route("/slots", methods=["GET"])
def slots():
    day = as_date(request.args.get("date"), "Date")
    check_booking_date(day)
    doctor = get_doctor(request.args.get("doctor_id"))
    check_doctor_works(doctor, day)
    return jsonify(free_slots(doctor["doctor_id"], day))


@bp.route("/appointments", methods=["GET"])
def my_appointments():
    return jsonify(query("""
        SELECT a.appointment_id, a.appointment_date, a.appointment_time, a.reason, a.status,
               a.notes, a.booked_via, d.specialization, d.consultation_fee,
               CONCAT('Dr. ', s.first_name,' ',s.last_name) AS doctor_name
        FROM appointments a
        JOIN doctors d ON d.doctor_id=a.doctor_id
        JOIN staff s ON s.staff_id=d.staff_id
        WHERE a.patient_id=%s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (me_id(),)))


@bp.route("/appointments", methods=["POST"])
def book_online():
    data = get_json()
    require(data, "doctor_id", "appointment_date", "appointment_time")
    day = as_date(data["appointment_date"], "Date")
    check_booking_date(day)
    at = parse_time(data["appointment_time"])
    if at.strftime("%H:%M") not in {s["time"] for s in free_slots(data["doctor_id"], day) if s["available"]}:
        abort(409, "That time is not available any more. Please pick another slot.")
    if query_one("""
        SELECT 1 FROM appointments
        WHERE patient_id=%s AND doctor_id=%s AND appointment_date=%s AND status='Scheduled'
    """, (me_id(), data["doctor_id"], day)):
        abort(409, "You already have an appointment with this doctor on that day.")
    new_id = book(me_id(), data["doctor_id"], day, at, data.get("reason"), "Online")
    return jsonify({"success": True, "appointment_id": new_id}), 201


@bp.route("/appointments/<int:aid>/cancel", methods=["POST"])
def cancel(aid):
    with transaction() as cur:
        cur.execute("""
            SELECT status, appointment_date FROM appointments
            WHERE appointment_id=%s AND patient_id=%s FOR UPDATE
        """, (aid, me_id()))
        appt = cur.fetchone()
        if not appt:
            abort(404, "Appointment not found.")
        if appt["status"] != "Scheduled" or appt["appointment_date"] < date.today():
            abort(409, "Only upcoming appointments can be cancelled.")
        cur.execute("UPDATE appointments SET status='Cancelled', notes=CONCAT_WS('\n', notes, 'Cancelled by patient online') "
                    "WHERE appointment_id=%s", (aid,))
    audit("Cancelled appointment online", f"A-{aid:03d}")
    return jsonify({"success": True})


# My records
@bp.route("/prescriptions", methods=["GET"])
def my_prescriptions():
    rows = query("""
        SELECT pr.prescription_id, pr.issued_date, pr.notes,
               CONCAT('Dr. ', s.first_name,' ',s.last_name) AS doctor_name, d.specialization
        FROM prescriptions pr
        JOIN doctors d ON d.doctor_id=pr.doctor_id
        JOIN staff s ON s.staff_id=d.staff_id
        WHERE pr.patient_id=%s ORDER BY pr.issued_date DESC
    """, (me_id(),))
    items = query("""
        SELECT pi.prescription_id, m.name, pi.dosage, pi.frequency, pi.duration_days, pi.qty_prescribed
        FROM prescription_items pi
        JOIN prescriptions pr ON pr.prescription_id=pi.prescription_id
        JOIN medicines m ON m.medicine_id=pi.medicine_id
        WHERE pr.patient_id=%s ORDER BY m.name
    """, (me_id(),))
    for row in rows:
        row["items"] = [i for i in items if i["prescription_id"] == row["prescription_id"]]
    return jsonify(rows)


@bp.route("/bills", methods=["GET"])
def my_bills():
    return jsonify(query("""
        SELECT bill_id, bill_date, due_date, total_amount, paid_amount, balance, status
        FROM bills WHERE patient_id=%s ORDER BY bill_date DESC
    """, (me_id(),)))


@bp.route("/bills/<int:bid>", methods=["GET"])
def my_bill(bid):
    bill = query_one("""
        SELECT b.*, CONCAT(p.first_name,' ',p.last_name) AS patient_name, p.phone, p.address
        FROM bills b JOIN patients p ON p.patient_id=b.patient_id
        WHERE b.bill_id=%s AND b.patient_id=%s
    """, (bid, me_id()))
    if not bill:
        abort(404, "Bill not found.")
    bill["items"] = query("SELECT * FROM bill_items WHERE bill_id=%s", (bid,))
    bill["payments"] = query("""
        SELECT payment_date, payment_method, transaction_ref, amount, NULL AS received_by_name
        FROM payments WHERE bill_id=%s ORDER BY payment_date
    """, (bid,))
    return jsonify(bill)
