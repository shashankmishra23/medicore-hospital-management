"""
Settings (admin only): whether sign-in needs a password, and every login
account in one place, for staff and for patients. Accounts are created here
and passwords are set here.
"""
import re

from flask import Blueprint, abort, jsonify

from audit import audit
from auth import STAFF_ROLES, current_user, hash_password, password_required, requires
from db import query, query_one, transaction
from utils import as_choice, check_email, clean, get_json, require

bp = Blueprint("settings", __name__, url_prefix="/api/settings")


@bp.route("", methods=["GET"])
@requires("settings.manage")
def get_settings():
    return jsonify({"require_password": password_required()})


@bp.route("", methods=["PUT"])
@requires("settings.manage")
def save_settings():
    data = get_json()
    if "require_password" not in data:
        abort(400, "Nothing to change.")
    on = bool(data["require_password"])
    with transaction() as cur:
        cur.execute("""
            INSERT INTO app_settings (setting_key, setting_value) VALUES ('require_password', %s)
            ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)
        """, ("1" if on else "0",))
    audit("Changed sign-in setting", "Password required" if on else "No password needed")
    return jsonify({"success": True, "require_password": on})


@bp.route("/accounts", methods=["GET"])
@requires("settings.manage")
def accounts():
    staff = query("""
        SELECT s.staff_id, CONCAT(s.first_name,' ',s.last_name) AS name, s.role AS job, s.status,
               u.user_id, u.username, u.role AS login_role, u.is_active, u.last_login,
               u.password_hash <> '' AS has_password,
               (u.locked_until IS NOT NULL AND u.locked_until > NOW()) AS locked
        FROM staff s
        LEFT JOIN system_users u ON u.staff_id=s.staff_id
        ORDER BY u.user_id IS NULL, s.first_name
    """)
    patients = query("""
        SELECT p.patient_id, CONCAT(p.first_name,' ',p.last_name) AS name, p.phone,
               a.account_id, a.email, a.is_active, a.last_login,
               a.password_hash <> '' AS has_password,
               (a.locked_until IS NOT NULL AND a.locked_until > NOW()) AS locked
        FROM patient_accounts a
        JOIN patients p ON p.patient_id=a.patient_id
        ORDER BY p.first_name
    """)
    for row in staff + patients:
        for flag in ("has_password", "locked", "is_active"):
            if row.get(flag) is not None:
                row[flag] = bool(row[flag])
    return jsonify({"staff": staff, "patients": patients})


# Staff accounts
def unique_username(first, last):
    """arun.sharma, or arun.sharma2 if that is taken."""
    base = re.sub(r"[^a-z0-9.]", "", f"{first}.{last}".lower()) or "user"
    name, n = base, 1
    while query_one("SELECT 1 FROM system_users WHERE username=%s", (name,)):
        n += 1
        name = f"{base}{n}"
    return name


@bp.route("/staff-accounts", methods=["POST"])
@requires("settings.manage")
def create_staff_account():
    data = get_json()
    require(data, "staff_id", "role")
    person = query_one("SELECT first_name, last_name FROM staff WHERE staff_id=%s", (data["staff_id"],))
    if not person:
        abort(404, "Staff member not found.")
    if query_one("SELECT 1 FROM system_users WHERE staff_id=%s", (data["staff_id"],)):
        abort(409, f"{person['first_name']} already has an account.")
    role = as_choice(data["role"], "Signs in as", STAFF_ROLES)
    password = hash_password(clean(data.get("password")))
    username = unique_username(person["first_name"], person["last_name"])
    with transaction() as cur:
        cur.execute("""
            INSERT INTO system_users (staff_id, username, password_hash, role) VALUES (%s,%s,%s,%s)
        """, (data["staff_id"], username, password, role))
    audit("Created staff account", f"{person['first_name']} {person['last_name']} ({role})")
    return jsonify({"success": True, "username": username}), 201


@bp.route("/staff-accounts/<int:uid>", methods=["PUT"])
@requires("settings.manage")
def update_staff_account(uid):
    return _update_account("system_users", "user_id", uid, get_json(), """
        SELECT CONCAT(s.first_name,' ',s.last_name) AS name FROM system_users u
        JOIN staff s ON s.staff_id=u.staff_id WHERE u.user_id=%s
    """)


# Patient portal accounts
@bp.route("/patient-accounts", methods=["POST"])
@requires("settings.manage")
def create_patient_account():
    data = get_json()
    require(data, "patient_id", "email")
    person = query_one("SELECT first_name, last_name FROM patients WHERE patient_id=%s", (data["patient_id"],))
    if not person:
        abort(404, "Patient not found.")
    if query_one("SELECT 1 FROM patient_accounts WHERE patient_id=%s", (data["patient_id"],)):
        abort(409, f"{person['first_name']} already has a portal account.")
    email = check_email(data["email"]).lower()
    password = hash_password(clean(data.get("password")))
    with transaction() as cur:
        cur.execute("INSERT INTO patient_accounts (patient_id, email, password_hash) VALUES (%s,%s,%s)",
                    (data["patient_id"], email, password))
    audit("Created patient account", f"{person['first_name']} {person['last_name']} ({email})")
    return jsonify({"success": True}), 201


@bp.route("/patient-accounts/<int:aid>", methods=["PUT"])
@requires("settings.manage")
def update_patient_account(aid):
    return _update_account("patient_accounts", "account_id", aid, get_json(), """
        SELECT CONCAT(p.first_name,' ',p.last_name) AS name FROM patient_accounts a
        JOIN patients p ON p.patient_id=a.patient_id WHERE a.account_id=%s
    """)


def _update_account(table, key, account_id, data, name_sql):
    """Set a new password and/or turn the account on or off. Setting a password also unlocks it."""
    account = query_one(name_sql, (account_id,))
    if not account:
        abort(404, "Account not found.")
    fields, params, done = [], [], []
    if clean(data.get("password")):
        fields += ["password_hash=%s", "failed_logins=0", "locked_until=NULL"]
        params.append(hash_password(data["password"].strip()))
        done.append("password set")
    if "is_active" in data:
        active = bool(data["is_active"])
        if not active and table == "system_users" and account_id == current_user()["user_id"]:
            abort(400, "You can't turn off your own account.")
        fields.append("is_active=%s")
        params.append(active)
        done.append("turned on" if active else "turned off")
    if not fields:
        abort(400, "Nothing to change.")
    with transaction() as cur:
        cur.execute(f"UPDATE {table} SET {', '.join(fields)} WHERE {key}=%s", (*params, account_id))
    audit("Changed account", f"{account['name']}: {', '.join(done)}")
    return jsonify({"success": True})
