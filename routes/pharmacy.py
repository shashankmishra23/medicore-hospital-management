"""
Medicines (stock), prescriptions written by doctors, and dispensing.
Dispensing a prescription takes the medicine out of stock.
"""
from datetime import date

from flask import Blueprint, abort, jsonify, request

from audit import audit
from auth import current_user, requires
from db import query, query_one, transaction
from utils import as_date, as_int, as_money, clean, get_json, require

bp = Blueprint("pharmacy", __name__, url_prefix="/api")


# Medicines
@bp.route("/medicines", methods=["GET"])
@requires("view.pharmacy")
def get_medicines():
    if request.args.get("low_stock", "false").lower() == "true":
        return jsonify(query("SELECT * FROM vw_low_stock_medicines ORDER BY stock_qty ASC"))
    search = request.args.get("search", "").strip()
    like = f"%{search}%"
    return jsonify(query("""
        SELECT * FROM medicines
        WHERE name LIKE %s OR generic_name LIKE %s OR category LIKE %s
        ORDER BY name
    """, (like, like, like)))


@bp.route("/medicines", methods=["POST"])
@requires("medicines.write")
def add_medicine():
    data = get_json()
    require(data, "name", "unit_price", "stock_qty")
    expiry = as_date(data["expiry_date"], "Expiry date") if clean(data.get("expiry_date")) else None
    if expiry and expiry <= date.today():
        abort(400, "Expiry date must be in the future.")
    with transaction() as cur:
        cur.execute("""
            INSERT INTO medicines
              (name,generic_name,category,manufacturer,unit,unit_price,
               stock_qty,reorder_level,expiry_date,requires_prescription)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            clean(data["name"]), clean(data.get("generic_name")), clean(data.get("category")),
            clean(data.get("manufacturer")), clean(data.get("unit")) or "Tablet",
            as_money(data["unit_price"], "Unit price"),
            as_int(data["stock_qty"], "Stock", minimum=0),
            as_int(data.get("reorder_level") or 10, "Reorder level", minimum=0),
            expiry, bool(data.get("requires_prescription", True)),
        ))
        new_id = cur.lastrowid
    audit("Added medicine", f"M-{new_id:03d} {clean(data['name'])}")
    return jsonify({"success": True, "medicine_id": new_id}), 201


@bp.route("/medicines/<int:mid>/restock", methods=["PUT"])
@requires("medicines.write")
def restock_medicine(mid):
    data = get_json()
    qty = as_int(data.get("quantity"), "Quantity", minimum=1)
    expiry = as_date(data["expiry_date"], "Expiry date") if clean(data.get("expiry_date")) else None
    with transaction() as cur:
        cur.execute("""
            UPDATE medicines
            SET stock_qty = stock_qty + %s, expiry_date = COALESCE(%s, expiry_date)
            WHERE medicine_id=%s
        """, (qty, expiry, mid))
        if cur.rowcount == 0:
            abort(404, "Medicine not found.")
    audit("Restocked medicine", f"M-{mid:03d} +{qty}")
    return jsonify({"success": True})


# Prescriptions
PRESCRIPTION_LIST = """
    SELECT pr.prescription_id, pr.patient_id, pr.doctor_id, pr.appointment_id,
           pr.issued_date, pr.notes,
           CONCAT(p.first_name,' ',p.last_name) AS patient_name,
           CONCAT(s.first_name,' ',s.last_name) AS doctor_name,
           COUNT(pi.item_id) AS item_count,
           GROUP_CONCAT(m.name ORDER BY m.name SEPARATOR ', ') AS medicines,
           -- dispensed when every item has been handed out in full
           CASE WHEN SUM(pi.qty_prescribed > COALESCE(dsp.qty, 0)) = 0
                THEN 'Dispensed' ELSE 'Pending' END AS status
    FROM prescriptions pr
    JOIN patients p ON p.patient_id=pr.patient_id
    JOIN doctors d ON d.doctor_id=pr.doctor_id
    JOIN staff s ON s.staff_id=d.staff_id
    JOIN prescription_items pi ON pi.prescription_id=pr.prescription_id
    JOIN medicines m ON m.medicine_id=pi.medicine_id
    LEFT JOIN (
        SELECT prescription_id, medicine_id, SUM(qty_dispensed) AS qty
        FROM pharmacy_dispensing GROUP BY prescription_id, medicine_id
    ) dsp ON dsp.prescription_id=pi.prescription_id AND dsp.medicine_id=pi.medicine_id
    GROUP BY pr.prescription_id
"""


@bp.route("/prescriptions", methods=["GET"])
@requires("view.prescriptions")
def get_prescriptions():
    status = request.args.get("status", "")
    sql = f"SELECT * FROM ({PRESCRIPTION_LIST}) x"
    if status:
        return jsonify(query(sql + " WHERE status=%s ORDER BY issued_date DESC", (status,)))
    return jsonify(query(sql + " ORDER BY status='Pending' DESC, issued_date DESC"))


@bp.route("/prescriptions/<int:pid>", methods=["GET"])
@requires("view.prescriptions")
def get_prescription(pid):
    pres = query_one(f"SELECT * FROM ({PRESCRIPTION_LIST}) x WHERE prescription_id=%s", (pid,))
    if not pres:
        abort(404, "Prescription not found.")
    pres["items"] = _items(pid)
    return jsonify(pres)


def _items(pid, cur=None):
    sql = """
        SELECT pi.*, m.name, m.unit, m.stock_qty, m.expiry_date, m.unit_price,
               COALESCE((SELECT SUM(qty_dispensed) FROM pharmacy_dispensing pd
                         WHERE pd.prescription_id=pi.prescription_id
                           AND pd.medicine_id=pi.medicine_id), 0) AS qty_dispensed
        FROM prescription_items pi
        JOIN medicines m ON m.medicine_id=pi.medicine_id
        WHERE pi.prescription_id=%s
        ORDER BY m.name
    """
    if cur is None:
        return query(sql, (pid,))
    cur.execute(sql, (pid,))
    return cur.fetchall()


@bp.route("/prescriptions", methods=["POST"])
@requires("prescriptions.write")
def add_prescription():
    data = get_json()
    user = current_user()
    # A doctor writes prescriptions in their own name
    doctor_id = user["doctor_id"] or data.get("doctor_id")
    require({**data, "doctor_id": doctor_id}, "patient_id", "doctor_id")
    items = data.get("items") or []
    if not items:
        abort(400, "Add at least one medicine.")

    rows = []
    for n, item in enumerate(items, start=1):
        if not clean(item.get("medicine_id")):
            abort(400, f"Choose a medicine on line {n}.")
        rows.append((
            as_int(item["medicine_id"], f"Medicine on line {n}"),
            clean(item.get("dosage")), clean(item.get("frequency")),
            as_int(item["duration_days"], f"Days on line {n}", minimum=1) if clean(item.get("duration_days")) else None,
            as_int(item.get("qty_prescribed"), f"Quantity on line {n}", minimum=1),
        ))
    if len({r[0] for r in rows}) != len(rows):
        abort(400, "The same medicine is listed twice. Put it on one line.")

    with transaction() as cur:
        cur.execute("""
            INSERT INTO prescriptions (patient_id, doctor_id, appointment_id, notes)
            VALUES (%s,%s,%s,%s)
        """, (data["patient_id"], doctor_id, clean(data.get("appointment_id")), clean(data.get("notes"))))
        pres_id = cur.lastrowid
        cur.executemany("""
            INSERT INTO prescription_items
              (prescription_id, medicine_id, dosage, frequency, duration_days, qty_prescribed)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, [(pres_id, *r) for r in rows])
    audit("Wrote prescription", f"RX-{pres_id:03d} for P-{int(data['patient_id']):03d}")
    return jsonify({"success": True, "prescription_id": pres_id}), 201


@bp.route("/prescriptions/<int:pid>/dispense", methods=["POST"])
@requires("prescriptions.dispense")
def dispense_prescription(pid):
    """Hand out everything still owed on the prescription. All or nothing."""
    with transaction() as cur:
        cur.execute("SELECT 1 FROM prescriptions WHERE prescription_id=%s", (pid,))
        if not cur.fetchone():
            abort(404, "Prescription not found.")
        # Lock the medicine rows so stock can't change while we check it
        cur.execute("""
            SELECT m.medicine_id FROM medicines m
            JOIN prescription_items pi ON pi.medicine_id=m.medicine_id
            WHERE pi.prescription_id=%s FOR UPDATE
        """, (pid,))
        items = _items(pid, cur)

        to_give, problems = [], []
        for it in items:
            owed = it["qty_prescribed"] - int(it["qty_dispensed"])
            if owed <= 0:
                continue
            if it["expiry_date"] and it["expiry_date"] < date.today():
                problems.append(f"{it['name']} has expired")
            elif it["stock_qty"] < owed:
                problems.append(f"{it['name']}: need {owed}, only {it['stock_qty']} in stock")
            else:
                to_give.append((it["medicine_id"], owed))
        if problems:
            abort(409, "Cannot dispense. " + "; ".join(problems) + ".")
        if not to_give:
            abort(409, "This prescription has already been dispensed.")

        staff_id = current_user()["staff_id"]
        for medicine_id, qty in to_give:
            cur.execute("""
                INSERT INTO pharmacy_dispensing (prescription_id, medicine_id, dispensed_by, qty_dispensed)
                VALUES (%s,%s,%s,%s)
            """, (pid, medicine_id, staff_id, qty))
            cur.execute("UPDATE medicines SET stock_qty=stock_qty-%s WHERE medicine_id=%s", (qty, medicine_id))

    audit("Dispensed prescription", f"RX-{pid:03d}")
    return jsonify({"success": True, "dispensed": len(to_give)})
