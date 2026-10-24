"""
Dashboard numbers, charts and the alerts bell.
Each role only gets the numbers for the pages it may open.
"""
from datetime import date

from flask import Blueprint, jsonify, request

from auth import can, requires
from db import query, query_one

bp = Blueprint("dashboard", __name__, url_prefix="/api")


def count(sql):
    return query_one(sql)["n"]


@bp.route("/dashboard", methods=["GET"])
def dashboard():
    stats = {}
    if can("view.patients"):
        stats["total_patients"] = count("SELECT COUNT(*) AS n FROM patients")
    if can("view.admissions"):
        stats["admitted"] = count("SELECT COUNT(*) AS n FROM patient_admissions WHERE status='Admitted'")
    if can("view.appointments"):
        stats["todays_appointments"] = count(
            "SELECT COUNT(*) AS n FROM appointments WHERE appointment_date=CURDATE() AND status='Scheduled'")
        stats["online_bookings"] = count("""
            SELECT COUNT(*) AS n FROM appointments
            WHERE booked_via='Online' AND created_at >= CURDATE() - INTERVAL 7 DAY""")
    if can("view.billing"):
        stats["monthly_revenue"] = count("""
            SELECT COALESCE(SUM(amount),0) AS n FROM payments
            WHERE YEAR(payment_date)=YEAR(CURDATE()) AND MONTH(payment_date)=MONTH(CURDATE())""")
        stats["outstanding"] = count(
            "SELECT COALESCE(SUM(balance),0) AS n FROM bills WHERE status IN ('Pending','Partial')")
    if can("view.staff"):
        stats["active_doctors"] = count("SELECT COUNT(*) AS n FROM staff WHERE status='Active' AND role='Doctor'")
    if can("view.wards"):
        stats["free_beds"] = count("SELECT COALESCE(SUM(available_beds),0) AS n FROM wards")
    if can("view.prescriptions"):
        stats["pending_prescriptions"] = count(f"SELECT COUNT(*) AS n FROM ({PENDING_RX}) x")
    if can("view.pharmacy"):
        stats["low_stock_medicines"] = count("SELECT COUNT(*) AS n FROM medicines WHERE stock_qty <= reorder_level")
    return jsonify(stats)


# Prescriptions with at least one medicine not yet handed out in full
PENDING_RX = """
    SELECT DISTINCT pi.prescription_id
    FROM prescription_items pi
    LEFT JOIN (SELECT prescription_id, medicine_id, SUM(qty_dispensed) AS qty
               FROM pharmacy_dispensing GROUP BY prescription_id, medicine_id) d
      ON d.prescription_id=pi.prescription_id AND d.medicine_id=pi.medicine_id
    WHERE pi.qty_prescribed > COALESCE(d.qty, 0)
"""


@bp.route("/dashboard/charts", methods=["GET"])
def charts():
    result = {}
    if can("view.billing"):
        # Revenue for the last 6 months, including months with no payments
        rows = query("""
            SELECT DATE_FORMAT(payment_date, '%Y-%m') AS month, SUM(amount) AS total
            FROM payments
            WHERE payment_date >= DATE_FORMAT(CURDATE() - INTERVAL 5 MONTH, '%Y-%m-01')
            GROUP BY month
        """)
        totals = {r["month"]: r["total"] for r in rows}
        today = date.today()
        result["revenue"] = []
        for back in range(5, -1, -1):
            y, m = divmod(today.year * 12 + today.month - 1 - back, 12)
            key = f"{y}-{m + 1:02d}"
            result["revenue"].append({"month": key, "total": totals.get(key, 0)})
    if can("view.appointments"):
        result["appointments"] = query("""
            SELECT status, COUNT(*) AS total FROM appointments
            WHERE appointment_date >= CURDATE() - INTERVAL 30 DAY
            GROUP BY status
        """)
    if can("view.wards"):
        result["beds"] = query("""
            SELECT ward_name, total_beds - available_beds AS occupied, available_beds AS free
            FROM wards ORDER BY ward_name
        """)
    return jsonify(result)


@bp.route("/alerts", methods=["GET"])
def get_alerts():
    """Collect everything that needs attention, most serious first.
    Only alerts about pages this role can open are included."""
    alerts = []

    if can("view.pharmacy"):
        for m in query("SELECT name, expiry_date FROM medicines WHERE expiry_date < CURDATE() ORDER BY expiry_date"):
            alerts.append({
                "type": "danger", "page": "pharmacy",
                "title": f"{m['name']} has expired",
                "detail": f"Expired on {m['expiry_date']:%d %b %Y}. Remove it from stock.",
            })

    if can("view.billing"):
        for b in query("""
            SELECT b.bill_id, b.balance,
                   CONCAT(p.first_name,' ',p.last_name) AS patient_name,
                   DATEDIFF(CURDATE(), b.due_date) AS days_late
            FROM bills b
            JOIN patients p ON p.patient_id=b.patient_id
            WHERE b.due_date < CURDATE() AND b.status IN ('Pending','Partial')
            ORDER BY b.due_date
        """):
            alerts.append({
                "type": "danger", "page": "billing",
                "title": f"Bill B-{b['bill_id']:03d} is overdue",
                "detail": f"{b['patient_name']} owes Rs {b['balance']:,.0f}, {b['days_late']} day(s) late.",
            })

    if can("view.wards"):
        for w in query("SELECT ward_name FROM wards WHERE available_beds <= 0 ORDER BY ward_name"):
            alerts.append({
                "type": "danger", "page": "wards",
                "title": f"{w['ward_name']} is full",
                "detail": "No free beds left in this ward.",
            })

    if can("view.pharmacy"):
        for m in query("""
            SELECT name, DATEDIFF(expiry_date, CURDATE()) AS days_left
            FROM medicines
            WHERE expiry_date BETWEEN CURDATE() AND CURDATE() + INTERVAL 30 DAY
            ORDER BY expiry_date
        """):
            alerts.append({
                "type": "warning", "page": "pharmacy",
                "title": f"{m['name']} expires soon",
                "detail": f"Expires in {m['days_left']} day(s).",
            })
        for m in query("""
            SELECT name, stock_qty, reorder_level FROM medicines
            WHERE stock_qty <= reorder_level ORDER BY stock_qty
        """):
            alerts.append({
                "type": "warning", "page": "pharmacy",
                "title": f"{m['name']} is low on stock",
                "detail": f"Only {m['stock_qty']} left (reorder level {m['reorder_level']}).",
            })

    if can("view.prescriptions"):
        n = count(f"SELECT COUNT(*) AS n FROM ({PENDING_RX}) x")
        if n:
            alerts.append({
                "type": "info", "page": "prescriptions",
                "title": f"{n} prescription(s) waiting",
                "detail": "Not yet dispensed by the pharmacy.",
            })

    if can("view.appointments"):
        n = count("""
            SELECT COUNT(*) AS n FROM appointments
            WHERE booked_via='Online' AND status='Scheduled' AND created_at >= NOW() - INTERVAL 1 DAY
        """)
        if n:
            alerts.append({
                "type": "info", "page": "appointments",
                "title": f"{n} new online booking(s)",
                "detail": "Booked by patients in the last 24 hours.",
            })
        n = count("""
            SELECT COUNT(*) AS n FROM appointments
            WHERE appointment_date=CURDATE() AND status='Scheduled'
        """)
        if n:
            alerts.append({
                "type": "info", "page": "appointments",
                "title": f"{n} appointment(s) today",
                "detail": "Still scheduled for today.",
            })

    return jsonify(alerts)


@bp.route("/activity", methods=["GET"])
@requires("view.activity")
def activity():
    search = request.args.get("search", "").strip()
    like = f"%{search}%"
    return jsonify(query("""
        SELECT * FROM audit_log
        WHERE actor_name LIKE %s OR action LIKE %s OR details LIKE %s OR actor_role LIKE %s
        ORDER BY log_id DESC LIMIT 300
    """, (like, like, like, like)))
