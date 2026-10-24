from datetime import date

from flask import Blueprint, abort, jsonify, request

from audit import audit
from auth import requires
from db import query, query_one, transaction
from utils import as_choice, as_date, as_money, check_email, check_phone, clean, get_json, require

bp = Blueprint("staff", __name__, url_prefix="/api")

STAFF_ROLES = ("Doctor", "Nurse", "Pharmacist", "Lab Technician", "Admin", "Receptionist", "Support")
STATUSES = ("Active", "Inactive", "On Leave")
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


@bp.route("/departments", methods=["GET"])
def get_departments():
    return jsonify(query("SELECT dept_id, dept_name, location FROM departments ORDER BY dept_name"))


@bp.route("/doctors", methods=["GET"])
def get_doctors():
    return jsonify(query("""
        SELECT d.doctor_id, d.specialization, d.qualification, d.consultation_fee,
               d.available_days, d.license_number,
               s.staff_id, s.first_name, s.last_name, s.email,
               s.phone, s.gender, s.status,
               dep.dept_name
        FROM doctors d
        JOIN staff s ON s.staff_id=d.staff_id
        LEFT JOIN departments dep ON dep.dept_id=s.dept_id
        ORDER BY s.first_name
    """))


@bp.route("/staff", methods=["GET"])
@requires("view.staff")
def get_staff():
    role = request.args.get("role", "")
    sql = """
        SELECT s.staff_id, s.first_name, s.last_name, s.role, s.email, s.phone,
               s.gender, s.hire_date, s.status, dep.dept_name,
               d.specialization, u.username, u.role AS login_role
        FROM staff s
        LEFT JOIN departments dep ON dep.dept_id=s.dept_id
        LEFT JOIN doctors d ON d.staff_id=s.staff_id
        LEFT JOIN system_users u ON u.staff_id=s.staff_id
    """
    if role:
        return jsonify(query(sql + " WHERE s.role=%s ORDER BY s.first_name", (role,)))
    return jsonify(query(sql + " ORDER BY s.role, s.first_name"))


@bp.route("/staff", methods=["POST"])
@requires("staff.write")
def add_staff():
    """Add a staff member. Doctors also get a doctors row. Logins are made on the Settings page."""
    data = get_json()
    require(data, "first_name", "last_name", "role", "email", "hire_date")
    role = as_choice(data["role"], "Role", STAFF_ROLES)
    hire_date = as_date(data["hire_date"], "Hire date")
    dob = as_date(data["dob"], "Date of birth") if clean(data.get("dob")) else None
    if dob and dob >= date.today():
        abort(400, "Date of birth must be in the past.")
    salary = as_money(data["salary"], "Salary", allow_zero=True) if clean(data.get("salary")) else None
    gender = clean(data.get("gender"))

    if role == "Doctor":
        require(data, "specialization", "license_number")
        days = data.get("available_days") or []
        if isinstance(days, str):
            days = days.split(",")
        days = [as_choice(d, "Available day", DAYS) for d in days]
        fee = as_money(data.get("consultation_fee") or 0, "Consultation fee", allow_zero=True)

    with transaction() as cur:
        cur.execute("""
            INSERT INTO staff
              (first_name,last_name,role,dept_id,email,phone,gender,dob,hire_date,salary)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            clean(data["first_name"]), clean(data["last_name"]), role,
            clean(data.get("dept_id")), check_email(data["email"]), check_phone(data.get("phone")),
            as_choice(gender, "Gender", ("Male", "Female", "Other")) if gender else None,
            dob, hire_date, salary,
        ))
        staff_id = cur.lastrowid

        if role == "Doctor":
            cur.execute("""
                INSERT INTO doctors
                  (staff_id, specialization, qualification, license_number, consultation_fee, available_days)
                VALUES (%s,%s,%s,%s,%s,%s)
            """, (
                staff_id, clean(data["specialization"]), clean(data.get("qualification")),
                clean(data["license_number"]), fee, ",".join(days),
            ))

    audit("Added staff member", f"{clean(data['first_name'])} {clean(data['last_name'])} ({role})")
    return jsonify({"success": True, "staff_id": staff_id}), 201


@bp.route("/staff/<int:sid>/status", methods=["PUT"])
@requires("staff.write")
def update_staff_status(sid):
    status = as_choice(get_json().get("status"), "Status", STATUSES)
    if not query_one("SELECT 1 FROM staff WHERE staff_id=%s", (sid,)):
        abort(404, "Staff member not found.")
    with transaction() as cur:
        cur.execute("UPDATE staff SET status=%s WHERE staff_id=%s", (status, sid))
        # Inactive staff cannot log in
        cur.execute("UPDATE system_users SET is_active=%s WHERE staff_id=%s", (status != "Inactive", sid))
    audit("Changed staff status", f"Staff #{sid} → {status}")
    return jsonify({"success": True})
