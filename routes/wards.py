from flask import Blueprint, abort, jsonify, request

from audit import audit
from auth import requires
from db import query, transaction
from utils import as_choice, get_json

bp = Blueprint("wards", __name__, url_prefix="/api")


@bp.route("/wards", methods=["GET"])
@requires("view.wards")
def get_wards():
    wards = query("""
        SELECT w.*, dep.dept_name,
               (w.total_beds - w.available_beds) AS occupied_beds
        FROM wards w
        LEFT JOIN departments dep ON dep.dept_id=w.dept_id
        ORDER BY w.ward_name
    """)
    # One query for all rooms instead of one per ward
    rooms = query("""
        SELECT r.*, CONCAT(p.first_name,' ',p.last_name) AS patient_name
        FROM rooms r
        LEFT JOIN patient_admissions a ON a.room_id=r.room_id AND a.status='Admitted'
        LEFT JOIN patients p ON p.patient_id=a.patient_id
        ORDER BY r.room_number
    """)
    by_ward = {}
    for room in rooms:
        by_ward.setdefault(room["ward_id"], []).append(room)
    for ward in wards:
        ward["rooms"] = by_ward.get(ward["ward_id"], [])
    return jsonify(wards)


@bp.route("/rooms", methods=["GET"])
@requires("view.wards")
def get_rooms():
    status = request.args.get("status", "")
    sql = """
        SELECT r.*, w.ward_name, w.ward_type, w.available_beds
        FROM rooms r JOIN wards w ON w.ward_id=r.ward_id
    """
    if status:
        return jsonify(query(sql + " WHERE r.status=%s ORDER BY r.room_number", (status,)))
    return jsonify(query(sql + " ORDER BY r.room_number"))


@bp.route("/rooms/<int:rid>/status", methods=["PUT"])
@requires("rooms.write")
def update_room_status(rid):
    """Switch a room between Available and Under Maintenance.
    'Occupied' is only set by admitting a patient."""
    status = as_choice(get_json().get("status"), "Status", ("Available", "Under Maintenance"))
    with transaction() as cur:
        cur.execute("SELECT status FROM rooms WHERE room_id=%s FOR UPDATE", (rid,))
        room = cur.fetchone()
        if not room:
            abort(404, "Room not found.")
        if room["status"] == "Occupied":
            abort(409, "A patient is in this room. Discharge them first.")
        cur.execute("UPDATE rooms SET status=%s WHERE room_id=%s", (status, rid))
    audit("Changed room status", f"Room #{rid} → {status}")
    return jsonify({"success": True})
