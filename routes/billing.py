from datetime import date
from decimal import Decimal

from flask import Blueprint, abort, jsonify, request

from audit import audit
from auth import current_user, requires
from db import query, query_one, transaction
from utils import as_choice, as_date, as_int, as_money, clean, get_json, require

bp = Blueprint("billing", __name__, url_prefix="/api")

ITEM_TYPES = ("Consultation", "Room", "Medicine", "Lab", "Surgery", "Procedure", "Other")
PAYMENT_METHODS = ("Cash", "Card", "UPI", "Net Banking", "Insurance", "Cheque")


@bp.route("/bills", methods=["GET"])
@requires("view.billing")
def get_bills():
    status = request.args.get("status", "")
    sql = """
        SELECT b.*, CONCAT(p.first_name,' ',p.last_name) AS patient_name
        FROM bills b
        JOIN patients p ON p.patient_id=b.patient_id
    """
    if status:
        return jsonify(query(sql + " WHERE b.status=%s ORDER BY b.bill_date DESC", (status,)))
    return jsonify(query(sql + " ORDER BY b.bill_date DESC"))


@bp.route("/bills/<int:bid>", methods=["GET"])
@requires("view.billing")
def get_bill(bid):
    bill = query_one("""
        SELECT b.*,
               CONCAT(p.first_name,' ',p.last_name) AS patient_name,
               p.phone, p.address
        FROM bills b
        JOIN patients p ON p.patient_id=b.patient_id
        WHERE b.bill_id=%s
    """, (bid,))
    if not bill:
        abort(404, "Bill not found.")
    bill["items"] = query("SELECT * FROM bill_items WHERE bill_id=%s", (bid,))
    bill["payments"] = query("""
        SELECT pay.*, CONCAT(s.first_name,' ',s.last_name) AS received_by_name
        FROM payments pay
        LEFT JOIN staff s ON s.staff_id=pay.received_by
        WHERE pay.bill_id=%s ORDER BY pay.payment_date
    """, (bid,))
    return jsonify(bill)


@bp.route("/bills", methods=["POST"])
@requires("billing.write")
def create_bill():
    """Make a bill from a list of items. Totals are worked out here, not trusted from the page."""
    data = get_json()
    require(data, "patient_id")
    items = data.get("items") or []
    if not items:
        abort(400, "Add at least one item.")

    rows = []
    for n, item in enumerate(items, start=1):
        if not clean(item.get("description")):
            abort(400, f"Write a description on line {n}.")
        qty = as_int(item.get("quantity") or 1, f"Quantity on line {n}", minimum=1)
        price = as_money(item.get("unit_price"), f"Price on line {n}")
        rows.append((clean(item["description"]),
                     as_choice(item.get("item_type") or "Other", f"Type on line {n}", ITEM_TYPES),
                     qty, price, qty * price))

    subtotal = sum(r[4] for r in rows)
    discount = as_money(data.get("discount") or 0, "Discount", allow_zero=True)
    if discount > subtotal:
        abort(400, "Discount cannot be more than the subtotal.")
    tax_percent = as_money(data.get("tax_percent") or 0, "Tax %", allow_zero=True)
    tax = ((subtotal - discount) * tax_percent / 100).quantize(Decimal("0.01"))
    total = subtotal - discount + tax
    due = as_date(data["due_date"], "Due date") if clean(data.get("due_date")) else None
    if due and due < date.today():
        abort(400, "Due date cannot be in the past.")

    if not query_one("SELECT 1 FROM patients WHERE patient_id=%s", (data["patient_id"],)):
        abort(400, "Patient not found.")
    with transaction() as cur:
        cur.execute("""
            INSERT INTO bills (patient_id, appointment_id, due_date, subtotal, discount, tax, total_amount, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (data["patient_id"], clean(data.get("appointment_id")), due,
              subtotal, discount, tax, total, clean(data.get("notes"))))
        bill_id = cur.lastrowid
        cur.executemany("""
            INSERT INTO bill_items (bill_id, description, item_type, quantity, unit_price, total_price)
            VALUES (%s,%s,%s,%s,%s,%s)
        """, [(bill_id, *r) for r in rows])
    audit("Created bill", f"B-{bill_id:03d} for Rs {total:,.2f}")
    return jsonify({"success": True, "bill_id": bill_id, "total_amount": total}), 201


@bp.route("/payments", methods=["POST"])
@requires("billing.write")
def record_payment():
    data = get_json()
    require(data, "bill_id", "amount", "payment_method")
    amount = as_money(data["amount"], "Amount")
    method = as_choice(data["payment_method"], "Payment method", PAYMENT_METHODS)

    with transaction() as cur:
        cur.execute(
            "SELECT total_amount, paid_amount, status FROM bills WHERE bill_id=%s FOR UPDATE",
            (data["bill_id"],)
        )
        bill = cur.fetchone()
        if not bill:
            abort(404, "Bill not found.")
        if bill["status"] in ("Paid", "Cancelled", "Refunded"):
            abort(400, f"This bill is already {bill['status']}.")

        balance = bill["total_amount"] - bill["paid_amount"]
        if amount > balance:
            abort(400, f"Amount is more than the balance (Rs {balance:,.2f}).")

        cur.execute("""
            INSERT INTO payments
              (bill_id, amount, payment_method, transaction_ref, received_by, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            data["bill_id"], amount, method, clean(data.get("transaction_ref")),
            current_user()["staff_id"], clean(data.get("notes")),
        ))
        payment_id = cur.lastrowid

        new_paid = bill["paid_amount"] + amount
        new_status = "Paid" if new_paid >= bill["total_amount"] else "Partial"
        cur.execute(
            "UPDATE bills SET paid_amount=%s, status=%s WHERE bill_id=%s",
            (new_paid, new_status, data["bill_id"])
        )
    audit("Recorded payment", f"Rs {amount:,.2f} {method} on B-{int(data['bill_id']):03d}")
    return jsonify({"success": True, "payment_id": payment_id, "status": new_status}), 201
