"""
Small shared helpers: JSON output, error handling and input checks.
"""
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

import pymysql
from flask import abort, current_app, jsonify, request
from flask.json.provider import DefaultJSONProvider
from werkzeug.exceptions import HTTPException, InternalServerError


class JSONProvider(DefaultJSONProvider):
    """Send dates as 2026-10-24, times as 09:30:00 and money as numbers."""

    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat(timespec="seconds")
        if isinstance(o, date):
            return o.isoformat()
        if isinstance(o, timedelta):  # MySQL TIME columns arrive as timedelta
            secs = int(o.total_seconds())
            return f"{secs // 3600:02d}:{secs % 3600 // 60:02d}:{secs % 60:02d}"
        if isinstance(o, Decimal):
            return float(o)
        return super().default(o)


def register_error_handlers(app):
    """Every API error goes back as {"error": "..."} so the page can show it."""

    @app.errorhandler(Exception)
    def handle_error(e):
        if not request.path.startswith("/api/"):
            if isinstance(e, HTTPException):
                return e
            current_app.logger.exception("Unexpected error")
            return InternalServerError()

        if isinstance(e, HTTPException):
            return jsonify({"error": e.description}), e.code

        if isinstance(e, pymysql.err.IntegrityError):
            code, msg = e.args[0], str(e.args[1]) if len(e.args) > 1 else str(e)
            if code == 1062:  # duplicate entry
                m = re.search(r"Duplicate entry '(.+?)'", msg)
                value = m.group(1) if m else "that value"
                return jsonify({"error": f"'{value}' is already in use."}), 409
            if code in (1451, 1452):
                return jsonify({"error": "A linked record does not exist or is still in use."}), 400
            return jsonify({"error": msg}), 400

        if isinstance(e, pymysql.err.OperationalError) and e.args and e.args[0] in (1045, 1049, 2003):
            return jsonify({"error": "Cannot connect to the database. Check the DB_ settings in your .env file."}), 503

        if isinstance(e, pymysql.err.DataError):
            return jsonify({"error": f"Invalid value: {e.args[-1]}"}), 400

        current_app.logger.exception("Unexpected error")
        detail = str(e) if current_app.debug else "Something went wrong on the server."
        return jsonify({"error": detail}), 500


# Input checks. Each one stops the request with a 400 and a readable message.

def get_json():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, "Request body must be JSON.")
    return data


def clean(value):
    """Trim text; treat empty strings as 'not given'."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def require(data, *fields):
    missing = [f for f in fields if clean(data.get(f)) is None]
    if missing:
        names = ", ".join(f.replace("_", " ") for f in missing)
        abort(400, f"Please fill in: {names}.")


def as_int(value, name, minimum=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        abort(400, f"{name} must be a whole number.")
    if minimum is not None and n < minimum:
        abort(400, f"{name} must be at least {minimum}.")
    return n


def as_money(value, name, allow_zero=False):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError, ValueError):
        abort(400, f"{name} must be a number.")
    if amount < 0 or (amount == 0 and not allow_zero):
        abort(400, f"{name} must be more than 0.")
    return amount


def as_date(value, name):
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        abort(400, f"{name} must be a date like 2026-01-31.")


def as_choice(value, name, choices):
    """Match case-insensitively and return the official spelling."""
    lookup = {c.lower(): c for c in choices}
    found = lookup.get(str(value or "").strip().lower())
    if not found:
        abort(400, f"{name} must be one of: {', '.join(choices)}.")
    return found


def check_phone(value, name="Phone"):
    value = clean(value)
    if value is None:
        return None
    digits = re.sub(r"[\s\-+()]", "", value)
    if not digits.isdigit() or not 7 <= len(digits) <= 15:
        abort(400, f"{name} must be 7 to 15 digits.")
    return value


def check_password_strength(password):
    password = password or ""
    if len(password) < 8 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        abort(400, "Password must be at least 8 characters and contain letters and numbers.")
    return password


def check_email(value):
    value = clean(value)
    if value is not None and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        abort(400, "Email address does not look right.")
    return value
