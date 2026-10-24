"""
Login, logout and permissions.

There are two kinds of users:
  • Staff (Admin, Doctor, Nurse, Pharmacist, Receptionist) use the main app at /
  • Patients use the online portal at /portal

Every /api/ route needs a logged-in staff member, and every /api/portal/ route
needs a logged-in patient (checked in _require_login). Routes also say which
permission they need, e.g. @requires("patients.write"), and only the roles
listed in PERMISSIONS have it. Admin has every permission.
"""
import secrets
from datetime import datetime
from functools import wraps

from flask import (Blueprint, abort, current_app, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from audit import audit
from db import query, query_one, transaction
from utils import as_choice, check_password_strength, get_json, require

bp = Blueprint("auth", __name__)

STAFF_ROLES = ("Admin", "Doctor", "Nurse", "Pharmacist", "Receptionist")

PERMISSIONS = {
    # Which pages (and the data behind them) each role may open
    "view.patients":      {"Doctor", "Nurse", "Pharmacist", "Receptionist"},
    "view.appointments":  {"Doctor", "Nurse", "Receptionist"},
    "view.admissions":    {"Doctor", "Nurse", "Receptionist"},
    "view.prescriptions": {"Doctor", "Nurse", "Pharmacist"},
    "view.pharmacy":      {"Doctor", "Pharmacist"},
    "view.billing":       {"Receptionist"},
    "view.staff":         {"Receptionist"},
    "view.wards":         {"Doctor", "Nurse", "Receptionist"},
    "view.activity":      set(),  # Admin only

    # What each role may change
    "patients.write":         {"Doctor", "Nurse", "Receptionist"},
    "appointments.write":     {"Doctor", "Receptionist"},
    "admissions.write":       {"Doctor", "Nurse"},
    "prescriptions.write":    {"Doctor"},
    "prescriptions.dispense": {"Pharmacist"},
    "medicines.write":        {"Pharmacist"},
    "billing.write":          {"Receptionist"},
    "rooms.write":            {"Nurse"},
    "staff.write":            set(),  # Admin only
}

# After this many wrong passwords in a row, the account is locked for a while
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15

PUBLIC_API = {"/api/auth/login", "/api/auth/logout", "/api/portal/login", "/api/portal/register"}
SET_PASSWORD_PATHS = {"/api/auth/me", "/api/auth/change-password", "/api/portal/me"}


def temporary_password():
    """One-time password that is easy to read out: no 0/O or 1/l, always letters and numbers."""
    letters, digits = "abcdefghjkmnpqrstuvwxyz", "23456789"
    return "".join(secrets.choice(letters) for _ in range(5)) + "".join(secrets.choice(digits) for _ in range(4))


def allowed_actions(role):
    return sorted(a for a, roles in PERMISSIONS.items() if role == "Admin" or role in roles)


def can(action):
    user = current_user()
    return bool(user) and action in allowed_actions(user["role"])


def current_user():
    """The logged-in staff member, or None."""
    return session.get("user")


def current_patient():
    """The logged-in patient (portal), or None."""
    return session.get("patient")


def requires(action):
    """Only let staff whose role has `action` call this route."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not can(action):
                abort(403, f"Your role ({current_user()['role']}) is not allowed to do this.")
            return view(*args, **kwargs)
        return wrapped
    return decorator


def _require_login():
    path = request.path
    if not path.startswith("/api/") or path in PUBLIC_API:
        return None
    if path.startswith("/api/portal/"):
        logged_in = current_patient()
    elif path == "/api/auth/change-password":
        logged_in = current_user() or current_patient()
    else:
        logged_in = current_user()
    if not logged_in:
        return jsonify({"error": "Please log in."}), 401
    # Someone signed in with a one-time password must choose their own first
    if logged_in.get("must_change_password") and path not in SET_PASSWORD_PATHS:
        return jsonify({"error": "Please set your own password first."}), 403
    # Writes must be JSON. Browsers cannot send JSON from another website
    # without permission, so this also blocks cross-site form tricks (CSRF).
    if request.method in ("POST", "PUT", "PATCH", "DELETE") and not request.is_json:
        return jsonify({"error": "Request body must be JSON."}), 415
    return None


def init_app(app):
    app.before_request(_require_login)
    app.register_blueprint(bp)


@bp.app_context_processor
def inject_hospital():
    return {"hospital": current_app.config["HOSPITAL"], "demo_mode": current_app.config["DEMO_MODE"]}


def verify_password(table, key, account, password):
    """
    Check a password for a row of system_users or patient_accounts.
    Too many wrong tries in a row lock the account for LOCK_MINUTES.
    In demo mode any password is accepted.
    """
    if current_app.config["DEMO_MODE"]:
        with transaction() as cur:
            cur.execute(f"UPDATE {table} SET last_login=NOW() WHERE {key}=%s", (account[key],))
        return

    now = datetime.now()
    if account["locked_until"] and account["locked_until"] > now:
        minutes = int((account["locked_until"] - now).total_seconds() // 60) + 1
        abort(429, f"Too many wrong attempts. This account is locked for {minutes} more minute(s).")

    if check_password_hash(account["password_hash"], password):
        with transaction() as cur:
            cur.execute(f"""
                UPDATE {table} SET failed_logins=0, locked_until=NULL, last_login=NOW()
                WHERE {key}=%s
            """, (account[key],))
        return

    with transaction() as cur:
        # A lock that has already run out starts the count again.
        # MySQL applies these left to right, so locked_until sees the new count.
        cur.execute(f"""
            UPDATE {table}
            SET failed_logins = IF(locked_until IS NOT NULL AND locked_until <= NOW(), 1, failed_logins + 1),
                locked_until  = IF(failed_logins >= %s, NOW() + INTERVAL %s MINUTE, NULL)
            WHERE {key}=%s
        """, (MAX_FAILED_LOGINS, LOCK_MINUTES, account[key]))
        cur.execute(f"SELECT failed_logins FROM {table} WHERE {key}=%s", (account[key],))
        failed = cur.fetchone()["failed_logins"]
    if failed >= MAX_FAILED_LOGINS:
        abort(429, f"Too many wrong attempts. This account is locked for {LOCK_MINUTES} minutes.")
    abort(401, "Wrong name or password.")


# Pages
@bp.route("/")
def index():
    if current_user():
        return render_template("index.html")
    if current_patient():
        return redirect(url_for("auth.portal"))
    return redirect(url_for("auth.login_page"))


@bp.route("/login")
def login_page():
    if current_user():
        return redirect(url_for("auth.index"))
    if current_patient():
        return redirect(url_for("auth.portal"))
    return render_template("login.html")


@bp.route("/portal")
def portal():
    if not current_patient():
        return redirect(url_for("auth.login_page") + "#patient")
    return render_template("portal.html")


# Staff login API
def find_staff_account(name, role=None):
    """
    Staff sign in with their name: full name ("Arun Sharma"), first name
    ("Arun") or username ("arun.sharma"), in any letter case.
    """
    name = " ".join(str(name).split())
    rows = query("""
        SELECT u.user_id, u.username, u.password_hash, u.role, u.is_active, u.must_change_password,
               u.failed_logins, u.locked_until,
               s.staff_id, s.first_name, s.last_name, s.status AS staff_status, d.doctor_id
        FROM system_users u
        JOIN staff s ON s.staff_id = u.staff_id
        LEFT JOIN doctors d ON d.staff_id = s.staff_id
        WHERE u.username = %s OR CONCAT(s.first_name, ' ', s.last_name) = %s OR s.first_name = %s
    """, (name, name, name))
    if role and any(r["role"] == role for r in rows):
        rows = [r for r in rows if r["role"] == role]
    if len(rows) > 1:
        exact = [r for r in rows if name.lower() in (r["username"].lower(), f"{r['first_name']} {r['last_name']}".lower())]
        if len(exact) != 1:
            abort(409, f"More than one person is called {name}. Please type your full name.")
        rows = exact
    return rows[0] if rows else None


@bp.route("/api/auth/login", methods=["POST"])
def login():
    data = get_json()
    data["name"] = data.get("name") or data.get("username")
    require(data, "name", "password")
    chosen = as_choice(data["role"], "Role", STAFF_ROLES) if data.get("role") else None
    user = find_staff_account(data["name"], chosen)

    # Same message for "no such person" and "wrong password", so nobody can
    # find out who has an account.
    if not user:
        abort(401, "Wrong name or password.")
    verify_password("system_users", "user_id", user, data["password"])

    if not user["is_active"] or user["staff_status"] == "Inactive":
        abort(403, "This account has been turned off. Please contact the hospital admin.")
    if chosen and chosen != user["role"]:
        article = "an" if chosen[0] in "AEIOU" else "a"
        abort(403, f"{user['first_name']} does not have {article} {chosen} account. Go back and choose {user['role']}.")

    session.clear()
    session.permanent = True
    session["user"] = {
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "staff_id": user["staff_id"],
        "doctor_id": user["doctor_id"],
        "name": f"{user['first_name']} {user['last_name']}",
        "must_change_password": bool(user["must_change_password"]) and not current_app.config["DEMO_MODE"],
    }
    audit("Signed in")
    return me()


@bp.route("/api/auth/logout", methods=["POST"])
def logout():
    if current_user() or current_patient():
        audit("Signed out")
    session.clear()
    return jsonify({"success": True})


@bp.route("/api/auth/me")
def me():
    user = current_user()
    return jsonify({**user, "permissions": allowed_actions(user["role"])})


@bp.route("/api/auth/change-password", methods=["POST"])
def change_password():
    """Works for staff and for patients."""
    data = get_json()
    require(data, "current_password", "new_password")
    check_password_strength(data["new_password"])
    kind = "user" if current_user() else "patient"
    if kind == "user":
        table, key, account_id = "system_users", "user_id", current_user()["user_id"]
    else:
        table, key, account_id = "patient_accounts", "account_id", current_patient()["account_id"]

    row = query_one(f"SELECT password_hash FROM {table} WHERE {key}=%s", (account_id,))
    if not check_password_hash(row["password_hash"], data["current_password"]):
        abort(400, "Your current password is not correct.")
    if data["current_password"] == data["new_password"]:
        abort(400, "The new password must be different from the old one.")
    with transaction() as cur:
        cur.execute(f"UPDATE {table} SET password_hash=%s, must_change_password=FALSE WHERE {key}=%s",
                    (generate_password_hash(data["new_password"]), account_id))
    session[kind] = {**session[kind], "must_change_password": False}
    audit("Changed password")
    return jsonify({"success": True})
