import secrets
from datetime import date

from flask import Blueprint, abort, jsonify, request
from werkzeug.security import generate_password_hash

from audit import audit
from auth import can, requires
from db import query, query_one, transaction
from utils import (as_choice, as_date, check_email, check_phone, clean,
                   get_json, require)

bp = Blueprint("patients", __name__, url_prefix="/api/patients")

GENDERS = ("Male", "Female", "Other")
BLOOD_GROUPS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")


def _patient_values(data):
    """Check the form and return the values in column order."""
    require(data, "first_name", "last_name", "dob", "gender", "phone")
    dob = as_date(data["dob"], "Date of birth")
    if dob > date.today():
        abort(400, "Date of birth cannot be in the future.")
    blood = clean(data.get("blood_group"))
    return (
        clean(data["first_name"]), clean(data["last_name"]), dob,
        as_choice(data["gender"], "Gender", GENDERS),
        as_choice(blood, "Blood group", BLOOD_GROUPS) if blood else None,
        check_phone(data["phone"]),
        check_email(data.get("email")),
        clean(data.get("address")),
        clean(data.get("emergency_contact_name")),
        check_phone(data.get("emergency_contact_phone"), "Emergency contact phone"),
        clean(data.get("medical_history")),
        clean(data.get("allergies")),
    )


COLUMNS = ("first_name", "last_name", "dob", "gender", "blood_group", "phone", "email",
           "address", "emergency_contact_name", "emergency_contact_phone",
           "medical_history", "allergies")


@bp.route("", methods=["GET"])
@requires("view.patients")
def list_patients():
    search = request.args.get("search", "").strip()
    sql = """
        SELECT p.*,
               a.admission_id, a.status AS admission_status,
               r.room_number, w.ward_name,
               CONCAT(s.first_name,' ',s.last_name) AS doctor_name
        FROM patients p
        LEFT JOIN patient_admissions a ON a.patient_id=p.patient_id AND a.status='Admitted'
        LEFT JOIN rooms r ON r.room_id=a.room_id
        LEFT JOIN wards w ON w.ward_id=r.ward_id
        LEFT JOIN doctors d ON d.doctor_id=a.admitted_by
        LEFT JOIN staff s ON s.staff_id=d.staff_id
        WHERE CONCAT(p.first_name,' ',p.last_name) LIKE %s OR p.phone LIKE %s OR p.patient_id = %s
        ORDER BY p.registered_at DESC, p.patient_id DESC
    """
    like = f"%{search}%"
    # "P-007" or "7" finds patient 7
    pid = search.upper().removeprefix("P-")
    pid = int(pid) if pid.isdigit() else -1
    return jsonify(query(sql, (like, like, pid)))


@bp.route("/<int:pid>", methods=["GET"])
@requires("view.patients")
def get_patient(pid):
    patient = query_one("SELECT * FROM patients WHERE patient_id=%s", (pid,))
    if not patient:
        abort(404, "Patient not found.")

    patient["admissions"] = query("""
        SELECT a.*, r.room_number, w.ward_name,
               CONCAT(s.first_name,' ',s.last_name) AS doctor_name
        FROM patient_admissions a
        LEFT JOIN rooms r ON r.room_id=a.room_id
        LEFT JOIN wards w ON w.ward_id=r.ward_id
        LEFT JOIN doctors d ON d.doctor_id=a.admitted_by
        LEFT JOIN staff s ON s.staff_id=d.staff_id
        WHERE a.patient_id=%s ORDER BY a.admission_date DESC
    """, (pid,))

    patient["appointments"] = query("""
        SELECT a.*, CONCAT(s.first_name,' ',s.last_name) AS doctor_name, d.specialization
        FROM appointments a
        JOIN doctors d ON d.doctor_id=a.doctor_id
        JOIN staff s ON s.staff_id=d.staff_id
        WHERE a.patient_id=%s
        ORDER BY a.appointment_date DESC, a.appointment_time DESC
    """, (pid,))

    # Each section is only sent to roles allowed to see it (None = hidden)
    patient["prescriptions"] = None if not can("view.prescriptions") else query("""
        SELECT pr.prescription_id, pr.issued_date, pr.notes,
               CONCAT(s.first_name,' ',s.last_name) AS doctor_name,
               GROUP_CONCAT(m.name ORDER BY m.name SEPARATOR ', ') AS medicines
        FROM prescriptions pr
        JOIN doctors d ON d.doctor_id=pr.doctor_id
        JOIN staff s ON s.staff_id=d.staff_id
        LEFT JOIN prescription_items pi ON pi.prescription_id=pr.prescription_id
        LEFT JOIN medicines m ON m.medicine_id=pi.medicine_id
        WHERE pr.patient_id=%s
        GROUP BY pr.prescription_id
        ORDER BY pr.issued_date DESC
    """, (pid,))

    patient["bills"] = None if not can("view.billing") else query("""
        SELECT bill_id, bill_date, due_date, total_amount, paid_amount, balance, status
        FROM bills WHERE patient_id=%s ORDER BY bill_date DESC
    """, (pid,))

    account = query_one("SELECT email, last_login FROM patient_accounts WHERE patient_id=%s", (pid,))
    patient["portal_email"] = account["email"] if account else None
    return jsonify(patient)


@bp.route("/<int:pid>/portal-access", methods=["POST"])
@requires("patients.write")
def give_portal_access(pid):
    """
    Reception gives an existing patient a portal login after checking their ID.
    A one-time password is shown to staff to hand over; the patient changes it later.
    """
    email = check_email(get_json().get("email"))
    if not email:
        abort(400, "Please enter the patient's email.")
    email = email.lower()
    if not query_one("SELECT 1 FROM patients WHERE patient_id=%s", (pid,)):
        abort(404, "Patient not found.")
    if query_one("SELECT 1 FROM patient_accounts WHERE patient_id=%s", (pid,)):
        abort(409, "This patient already has portal access.")

    # Easy to read out loud: no 0/O or 1/l, always letters and numbers
    letters, digits = "abcdefghjkmnpqrstuvwxyz", "23456789"
    password = "".join(secrets.choice(letters) for _ in range(5)) + "".join(secrets.choice(digits) for _ in range(4))
    with transaction() as cur:
        cur.execute("INSERT INTO patient_accounts (patient_id, email, password_hash) VALUES (%s,%s,%s)",
                    (pid, email, generate_password_hash(password)))
    audit("Gave portal access", f"P-{pid:03d} ({email})")
    return jsonify({"success": True, "email": email, "temporary_password": password}), 201


@bp.route("", methods=["POST"])
@requires("patients.write")
def add_patient():
    values = _patient_values(get_json())
    with transaction() as cur:
        cur.execute(
            f"INSERT INTO patients ({', '.join(COLUMNS)}) VALUES ({', '.join(['%s'] * len(COLUMNS))})",
            values,
        )
        new_id = cur.lastrowid
    audit("Added patient", f"P-{new_id:03d} {values[0]} {values[1]}")
    return jsonify({"success": True, "patient_id": new_id}), 201


@bp.route("/<int:pid>", methods=["PUT"])
@requires("patients.write")
def update_patient(pid):
    values = _patient_values(get_json())
    with transaction() as cur:
        cur.execute(
            f"UPDATE patients SET {', '.join(c + '=%s' for c in COLUMNS)} WHERE patient_id=%s",
            (*values, pid),
        )
        if cur.rowcount == 0 and not query_one("SELECT 1 FROM patients WHERE patient_id=%s", (pid,)):
            abort(404, "Patient not found.")
    audit("Edited patient", f"P-{pid:03d} {values[0]} {values[1]}")
    return jsonify({"success": True})
