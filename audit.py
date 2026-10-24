"""
Activity log: remember who did what, so the admin can review it later.

    audit("Added patient", "P-012 Ravi Kumar")
"""
from flask import current_app, request, session

from db import transaction


def audit(action, details="", actor=None):
    """Save one line in the activity log. Never stops the request if it fails."""
    staff, patient = session.get("user"), session.get("patient")
    if actor:
        kind, actor_id, name, role = actor
    elif staff:
        kind, actor_id, name, role = "Staff", staff["user_id"], staff["name"], staff["role"]
    elif patient:
        kind, actor_id, name, role = "Patient", patient["account_id"], patient["name"], "Patient"
    else:
        kind, actor_id, name, role = "System", None, None, None
    try:
        with transaction() as cur:
            cur.execute("""
                INSERT INTO audit_log (actor_type, actor_id, actor_name, actor_role, action, details, ip_address)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """, (kind, actor_id, name, role, action, str(details)[:255], request.remote_addr))
    except Exception:
        current_app.logger.exception("Could not write to the activity log")
