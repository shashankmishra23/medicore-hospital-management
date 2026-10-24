"""
Admit a patient to a room and discharge them.
Rooms and ward bed counts are kept up to date automatically,
and a bill can be created on discharge.
"""
from datetime import date, timedelta
from decimal import Decimal

from flask import Blueprint, abort, jsonify, request

from audit import audit
from auth import requires
from db import query, transaction
from utils import as_int, clean, get_json, require

bp = Blueprint("admissions", __name__, url_prefix="/api/admissions")


@bp.route("", methods=["GET"])
@requires("view.admissions")
def get_admissions():
    status = request.args.get("status", "")
    sql = """
        SELECT a.*,
               CONCAT(p.first_name,' ',p.last_name) AS patient_name, p.gender, p.dob,
               r.room_number, r.daily_rate, w.ward_name,
               CONCAT(s.first_name,' ',s.last_name) AS doctor_name,
               GREATEST(1, DATEDIFF(COALESCE(a.discharge_date, NOW()), a.admission_date)) AS days
        FROM patient_admissions a
        JOIN patients p ON p.patient_id=a.patient_id
        LEFT JOIN rooms r ON r.room_id=a.room_id
        LEFT JOIN wards w ON w.ward_id=r.ward_id
        LEFT JOIN doctors d ON d.doctor_id=a.admitted_by
        LEFT JOIN staff s ON s.staff_id=d.staff_id
    """
    if status:
        return jsonify(query(sql + " WHERE a.status=%s ORDER BY a.admission_date DESC", (status,)))
    return jsonify(query(sql + " ORDER BY a.status='Admitted' DESC, a.admission_date DESC"))


@bp.route("", methods=["POST"])
@requires("admissions.write")
def admit_patient():
    data = get_json()
    require(data, "patient_id", "room_id", "doctor_id", "diagnosis")
    patient_id = as_int(data["patient_id"], "Patient")
    room_id = as_int(data["room_id"], "Room")

    with transaction() as cur:
        cur.execute("SELECT 1 FROM patients WHERE patient_id=%s", (patient_id,))
        if not cur.fetchone():
            abort(400, "Patient not found.")
        cur.execute("SELECT 1 FROM doctors WHERE doctor_id=%s", (data["doctor_id"],))
        if not cur.fetchone():
            abort(400, "Doctor not found.")
        cur.execute("""
            SELECT 1 FROM patient_admissions
            WHERE patient_id=%s AND status='Admitted' FOR UPDATE
        """, (patient_id,))
        if cur.fetchone():
            abort(409, "This patient is already admitted.")

        # Lock the room and ward rows so two people can't take the same bed
        cur.execute("""
            SELECT r.room_number, r.status, w.ward_id, w.ward_name, w.available_beds
            FROM rooms r JOIN wards w ON w.ward_id=r.ward_id
            WHERE r.room_id=%s FOR UPDATE
        """, (room_id,))
        room = cur.fetchone()
        if not room:
            abort(400, "Room not found.")
        if room["status"] != "Available":
            abort(409, f"Room {room['room_number']} is {room['status'].lower()}.")
        if room["available_beds"] <= 0:
            abort(409, f"{room['ward_name']} has no free beds.")

        cur.execute("""
            INSERT INTO patient_admissions (patient_id, room_id, admitted_by, diagnosis, notes)
            VALUES (%s,%s,%s,%s,%s)
        """, (patient_id, room_id, data["doctor_id"], clean(data["diagnosis"]), clean(data.get("notes"))))
        admission_id = cur.lastrowid
        cur.execute("UPDATE rooms SET status='Occupied' WHERE room_id=%s", (room_id,))
        cur.execute("UPDATE wards SET available_beds=available_beds-1 WHERE ward_id=%s", (room["ward_id"],))

    audit("Admitted patient", f"P-{patient_id:03d} to room {room['room_number']}")
    return jsonify({"success": True, "admission_id": admission_id}), 201


@bp.route("/<int:aid>/discharge", methods=["POST"])
@requires("admissions.write")
def discharge_patient(aid):
    data = get_json()
    bill_id = None

    with transaction() as cur:
        cur.execute("""
            SELECT a.*, r.room_number, r.daily_rate, r.ward_id, d.consultation_fee,
                   GREATEST(1, DATEDIFF(NOW(), a.admission_date)) AS days
            FROM patient_admissions a
            LEFT JOIN rooms r ON r.room_id=a.room_id
            LEFT JOIN doctors d ON d.doctor_id=a.admitted_by
            WHERE a.admission_id=%s FOR UPDATE
        """, (aid,))
        adm = cur.fetchone()
        if not adm:
            abort(404, "Admission not found.")
        if adm["status"] != "Admitted":
            abort(409, f"This patient is already {adm['status'].lower()}.")

        notes = clean(data.get("notes"))
        cur.execute("""
            UPDATE patient_admissions
            SET status='Discharged', discharge_date=NOW(),
                notes=CONCAT_WS('\n', notes, %s)
            WHERE admission_id=%s
        """, (notes, aid))
        if adm["room_id"]:
            cur.execute("UPDATE rooms SET status='Available' WHERE room_id=%s", (adm["room_id"],))
            cur.execute("""
                UPDATE wards SET available_beds=LEAST(total_beds, available_beds+1)
                WHERE ward_id=%s
            """, (adm["ward_id"],))

        if data.get("create_bill"):
            bill_id = _create_discharge_bill(cur, adm)

    audit("Discharged patient", f"P-{adm['patient_id']:03d}" + (f", bill B-{bill_id:03d}" if bill_id else ""))
    return jsonify({"success": True, "bill_id": bill_id})


def _create_discharge_bill(cur, adm):
    """Bill for the room, the doctor's fee and any medicine given during the stay."""
    items = []
    if adm["room_id"]:
        days = adm["days"]
        items.append((f"Room {adm['room_number']} ({days} day{'s' if days > 1 else ''})",
                      "Room", days, adm["daily_rate"]))
    if adm["consultation_fee"]:
        items.append(("Doctor consultation", "Consultation", 1, adm["consultation_fee"]))

    cur.execute("""
        SELECT m.name, m.unit_price, SUM(pd.qty_dispensed) AS qty
        FROM pharmacy_dispensing pd
        JOIN prescriptions pr ON pr.prescription_id=pd.prescription_id
        JOIN medicines m ON m.medicine_id=pd.medicine_id
        WHERE pr.patient_id=%s AND pd.dispense_date >= %s
        GROUP BY m.medicine_id
    """, (adm["patient_id"], adm["admission_date"]))
    for med in cur.fetchall():
        items.append((med["name"], "Medicine", int(med["qty"]), med["unit_price"]))

    subtotal = sum(Decimal(qty) * Decimal(price) for _, _, qty, price in items)
    cur.execute("""
        INSERT INTO bills (patient_id, admission_id, due_date, subtotal, total_amount, notes)
        VALUES (%s,%s,%s,%s,%s,'Created automatically on discharge')
    """, (adm["patient_id"], adm["admission_id"], date.today() + timedelta(days=7), subtotal, subtotal))
    bill_id = cur.lastrowid
    cur.executemany("""
        INSERT INTO bill_items (bill_id, description, item_type, quantity, unit_price, total_price)
        VALUES (%s,%s,%s,%s,%s,%s)
    """, [(bill_id, desc, kind, qty, price, Decimal(qty) * Decimal(price)) for desc, kind, qty, price in items])
    return bill_id
