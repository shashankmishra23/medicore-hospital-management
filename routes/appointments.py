from datetime import date, datetime, time, timedelta

from flask import Blueprint, abort, jsonify, request

from audit import audit
from auth import requires
from db import query, query_one, transaction
from utils import as_choice, as_date, clean, get_json, require

bp = Blueprint("appointments", __name__, url_prefix="/api/appointments")

STATUSES = ("Scheduled", "Completed", "Cancelled", "No-Show")
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# OPD hours: 9:00–13:00 and 14:00–17:00, one patient every 30 minutes
SLOT_MINUTES = 30
SESSIONS = ((time(9, 0), time(13, 0)), (time(14, 0), time(17, 0)))


def all_slots():
    slots = []
    for start, end in SESSIONS:
        t = datetime.combine(date.today(), start)
        while t.time() < end:
            slots.append(t.time())
            t += timedelta(minutes=SLOT_MINUTES)
    return slots


def get_doctor(doctor_id):
    doctor = query_one("""
        SELECT d.doctor_id, d.available_days, d.consultation_fee, d.specialization, s.status,
               CONCAT('Dr. ', s.first_name,' ',s.last_name) AS name
        FROM doctors d JOIN staff s ON s.staff_id=d.staff_id
        WHERE d.doctor_id=%s
    """, (doctor_id,))
    if not doctor:
        abort(400, "Doctor not found.")
    days = doctor["available_days"] or ""
    doctor["days"] = set(days.split(",")) if isinstance(days, str) else set(days)
    doctor["days"].discard("")
    return doctor


def check_doctor_works(doctor, day):
    if doctor["status"] != "Active":
        abort(400, f"{doctor['name']} is currently {doctor['status']}.")
    weekday = WEEKDAYS[day.weekday()]
    if doctor["days"] and weekday not in doctor["days"]:
        days = ", ".join(d for d in WEEKDAYS if d in doctor["days"])
        abort(400, f"{doctor['name']} does not work on {weekday}. Working days: {days}.")


def free_slots(doctor_id, day):
    """Every OPD slot for that day, marked free or taken."""
    taken = {r["appointment_time"] for r in query("""
        SELECT appointment_time FROM appointments
        WHERE doctor_id=%s AND appointment_date=%s AND status='Scheduled'
    """, (doctor_id, day))}
    taken = {(datetime.min + t).time() if isinstance(t, timedelta) else t for t in taken}
    now = datetime.now()
    return [{"time": s.strftime("%H:%M"), "available": s not in taken and datetime.combine(day, s) > now}
            for s in all_slots()]


def book(patient_id, doctor_id, day, at, reason, booked_via):
    """Book one appointment after checking every rule. Used by staff and by the patient portal."""
    if datetime.combine(day, at) < datetime.now():
        abort(400, "Appointment cannot be in the past.")
    if not query_one("SELECT 1 FROM patients WHERE patient_id=%s", (patient_id,)):
        abort(400, "Patient not found.")
    doctor = get_doctor(doctor_id)
    check_doctor_works(doctor, day)

    with transaction() as cur:
        cur.execute("""
            SELECT appointment_id FROM appointments
            WHERE doctor_id=%s AND appointment_date=%s AND appointment_time=%s AND status='Scheduled'
            FOR UPDATE
        """, (doctor_id, day, at))
        if cur.fetchone():
            abort(409, f"{doctor['name']} already has an appointment at that time.")
        cur.execute("""
            INSERT INTO appointments
              (patient_id, doctor_id, appointment_date, appointment_time, reason, booked_via)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, (patient_id, doctor_id, day, at, clean(reason), booked_via))
        new_id = cur.lastrowid
    audit("Booked appointment", f"A-{new_id:03d} with {doctor['name']} on {day:%d %b %Y} {at:%H:%M}")
    return new_id


def parse_time(value):
    try:
        return datetime.strptime(str(value)[:5], "%H:%M").time()
    except ValueError:
        abort(400, "Appointment time must look like 14:30.")


@bp.route("", methods=["GET"])
@requires("view.appointments")
def get_appointments():
    sql = """
        SELECT a.*,
               CONCAT(p.first_name,' ',p.last_name) AS patient_name,
               CONCAT(s.first_name,' ',s.last_name) AS doctor_name,
               d.specialization
        FROM appointments a
        JOIN patients p ON p.patient_id=a.patient_id
        JOIN doctors d  ON d.doctor_id=a.doctor_id
        JOIN staff s    ON s.staff_id=d.staff_id
        WHERE 1=1
    """
    params = []
    for arg, column in (("date", "a.appointment_date"), ("status", "a.status"), ("booked_via", "a.booked_via"),
                        ("doctor_id", "a.doctor_id"), ("patient_id", "a.patient_id")):
        value = request.args.get(arg, "")
        if value:
            sql += f" AND {column}=%s"
            params.append(value)
    sql += " ORDER BY a.appointment_date DESC, a.appointment_time ASC"
    return jsonify(query(sql, params))


@bp.route("/slots", methods=["GET"])
@requires("appointments.write")
def get_slots():
    day = as_date(request.args.get("date"), "Date")
    doctor = get_doctor(request.args.get("doctor_id"))
    check_doctor_works(doctor, day)
    return jsonify(free_slots(doctor["doctor_id"], day))


@bp.route("", methods=["POST"])
@requires("appointments.write")
def book_appointment():
    data = get_json()
    require(data, "patient_id", "doctor_id", "appointment_date", "appointment_time")
    new_id = book(data["patient_id"], data["doctor_id"],
                  as_date(data["appointment_date"], "Appointment date"),
                  parse_time(data["appointment_time"]), data.get("reason"), "Staff")
    return jsonify({"success": True, "appointment_id": new_id}), 201


@bp.route("/<int:aid>", methods=["PUT"])
@requires("appointments.write")
def update_appointment(aid):
    data = get_json()

    # Only change the fields that were actually sent
    fields, params = [], []
    if "status" in data:
        fields.append("status=%s")
        params.append(as_choice(data["status"], "Status", STATUSES))
    if "notes" in data:
        fields.append("notes=%s")
        params.append(clean(data["notes"]))
    if not fields:
        abort(400, "Nothing to update.")

    if not query_one("SELECT 1 FROM appointments WHERE appointment_id=%s", (aid,)):
        abort(404, "Appointment not found.")
    with transaction() as cur:
        cur.execute(f"UPDATE appointments SET {', '.join(fields)} WHERE appointment_id=%s", (*params, aid))
    audit("Updated appointment", f"A-{aid:03d}" + (f" → {params[0]}" if "status" in data else ""))
    return jsonify({"success": True})
