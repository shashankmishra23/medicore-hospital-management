from datetime import date, timedelta

from conftest import login

NEW_PATIENT = {
    "first_name": "Test", "last_name": "Patient", "dob": "1990-01-15",
    "gender": "Female", "phone": "9000000001", "blood_group": "O+",
}


def next_weekday(weekday, after=1):
    """The next date (at least `after` days ahead) that falls on `weekday` (0 = Monday)."""
    d = date.today() + timedelta(days=after)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d.isoformat()


def add_patient(client, **changes):
    r = client.post("/api/patients", json={**NEW_PATIENT, **changes})
    assert r.status_code == 201, r.get_json()
    return r.get_json()["patient_id"]


# Login
def test_pages_and_api_need_login(client):
    assert client.get("/").status_code == 302
    assert client.get("/api/patients").status_code == 401


def test_wrong_password_is_rejected(client):
    r = client.post("/api/auth/login", json={"name": "Shashank Mishra", "password": "wrong"})
    assert r.status_code == 401
    assert r.get_json()["error"] == "Wrong name or password."


def test_login_returns_role_and_permissions(admin):
    me = admin.get("/api/auth/me").get_json()
    assert me["role"] == "Admin"
    assert "staff.write" in me["permissions"]
    assert admin.get("/").status_code == 200


def test_writes_must_be_json(admin):
    r = admin.post("/api/patients", data={"first_name": "x"})
    assert r.status_code == 415


# Permissions
def test_pharmacist_cannot_add_patients(client):
    login(client, "pharmacist")
    r = client.post("/api/patients", json=NEW_PATIENT)
    assert r.status_code == 403


def test_nurse_cannot_add_staff(client):
    login(client, "nurse")
    r = client.post("/api/staff", json={"first_name": "X"})
    assert r.status_code == 403


# Patients
def test_patient_form_is_checked(admin):
    assert admin.post("/api/patients", json={"first_name": "Only"}).status_code == 400
    assert admin.post("/api/patients", json={**NEW_PATIENT, "phone": "12ab"}).status_code == 400
    future = (date.today() + timedelta(days=3)).isoformat()
    assert admin.post("/api/patients", json={**NEW_PATIENT, "dob": future}).status_code == 400


def test_add_edit_and_find_patient(admin):
    pid = add_patient(admin)
    r = admin.put(f"/api/patients/{pid}", json={**NEW_PATIENT, "allergies": "Penicillin"})
    assert r.status_code == 200
    patient = admin.get(f"/api/patients/{pid}").get_json()
    assert patient["allergies"] == "Penicillin"
    found = admin.get(f"/api/patients?search=P-{pid:03d}").get_json()
    assert [p["patient_id"] for p in found] == [pid]


# Appointments
def test_appointment_rules(admin):
    pid = add_patient(admin)
    monday = next_weekday(0)
    sunday = next_weekday(6)
    booking = {"patient_id": pid, "doctor_id": 1, "appointment_date": monday, "appointment_time": "10:15"}

    # Dr. Arun Sharma (doctor 1) does not work on Sundays
    r = admin.post("/api/appointments", json={**booking, "appointment_date": sunday})
    assert r.status_code == 400 and "does not work" in r.get_json()["error"]

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert admin.post("/api/appointments", json={**booking, "appointment_date": yesterday}).status_code == 400

    assert admin.post("/api/appointments", json=booking).status_code == 201
    # Same doctor, same time: refused
    assert admin.post("/api/appointments", json=booking).status_code == 409


def test_update_appointment_status(admin):
    r = admin.put("/api/appointments/1", json={"status": "completed", "notes": "All fine"})
    assert r.status_code == 200
    assert admin.put("/api/appointments/1", json={"status": "Maybe"}).status_code == 400


# Admissions
def free_room(client):
    return client.get("/api/rooms?status=Available").get_json()[0]


def ward_free_beds(client, ward_name):
    return next(w for w in client.get("/api/wards").get_json() if w["ward_name"] == ward_name)["available_beds"]


def test_admit_and_discharge_with_bill(admin):
    pid = add_patient(admin)
    room = free_room(admin)
    beds_before = ward_free_beds(admin, room["ward_name"])

    r = admin.post("/api/admissions", json={"patient_id": pid, "room_id": room["room_id"],
                                            "doctor_id": 1, "diagnosis": "Observation"})
    assert r.status_code == 201
    aid = r.get_json()["admission_id"]
    assert ward_free_beds(admin, room["ward_name"]) == beds_before - 1

    # Can't admit the same patient twice, or put someone else in the same room
    again = {"patient_id": pid, "room_id": room["room_id"], "doctor_id": 1, "diagnosis": "x"}
    assert admin.post("/api/admissions", json=again).status_code == 409
    other = add_patient(admin, phone="9000000002")
    assert admin.post("/api/admissions", json={**again, "patient_id": other}).status_code == 409

    r = admin.post(f"/api/admissions/{aid}/discharge", json={"create_bill": True})
    assert r.status_code == 200
    bill = admin.get(f"/api/bills/{r.get_json()['bill_id']}").get_json()
    assert bill["total_amount"] == float(room["daily_rate"]) + 800  # 1 day + Dr. Sharma's fee
    assert ward_free_beds(admin, room["ward_name"]) == beds_before
    assert admin.post(f"/api/admissions/{aid}/discharge", json={}).status_code == 409


# Prescriptions & pharmacy
def stock(client, medicine_id):
    return next(m for m in client.get("/api/medicines").get_json() if m["medicine_id"] == medicine_id)["stock_qty"]


def test_dispensing_takes_medicine_out_of_stock(admin):
    pid = add_patient(admin)
    r = admin.post("/api/prescriptions", json={
        "patient_id": pid, "doctor_id": 2,
        "items": [{"medicine_id": 4, "dosage": "500mg", "frequency": "Twice daily", "qty_prescribed": 6}],
    })
    assert r.status_code == 201
    rx = r.get_json()["prescription_id"]
    before = stock(admin, 4)

    assert admin.post(f"/api/prescriptions/{rx}/dispense", json={}).status_code == 200
    assert stock(admin, 4) == before - 6
    assert admin.get(f"/api/prescriptions/{rx}").get_json()["status"] == "Dispensed"
    assert admin.post(f"/api/prescriptions/{rx}/dispense", json={}).status_code == 409


def test_cannot_dispense_more_than_stock_or_expired(admin):
    pid = add_patient(admin)
    too_much = admin.post("/api/prescriptions", json={
        "patient_id": pid, "doctor_id": 1, "items": [{"medicine_id": 8, "qty_prescribed": 9999}]}).get_json()
    r = admin.post(f"/api/prescriptions/{too_much['prescription_id']}/dispense", json={})
    assert r.status_code == 409 and "in stock" in r.get_json()["error"]

    expired = admin.post("/api/prescriptions", json={   # medicine 3 expired in the sample data
        "patient_id": pid, "doctor_id": 1, "items": [{"medicine_id": 3, "qty_prescribed": 1}]}).get_json()
    r = admin.post(f"/api/prescriptions/{expired['prescription_id']}/dispense", json={})
    assert r.status_code == 409 and "expired" in r.get_json()["error"]


def test_doctor_prescribes_in_own_name(client):
    login(client, "doctor")  # Dr. Arun Sharma, doctor_id 1
    r = client.post("/api/prescriptions", json={"patient_id": 2, "doctor_id": 3,
                                                "items": [{"medicine_id": 4, "qty_prescribed": 2}]})
    rx = client.get(f"/api/prescriptions/{r.get_json()['prescription_id']}").get_json()
    assert rx["doctor_id"] == 1


def test_restock(admin):
    before = stock(admin, 5)
    assert admin.put("/api/medicines/5/restock", json={"quantity": 20}).status_code == 200
    assert stock(admin, 5) == before + 20
    assert admin.put("/api/medicines/5/restock", json={"quantity": 0}).status_code == 400


# Billing
def test_bill_totals_are_worked_out_on_the_server(admin):
    r = admin.post("/api/bills", json={
        "patient_id": 2, "discount": 100, "tax_percent": 10,
        "items": [{"description": "X-Ray", "item_type": "Lab", "quantity": 2, "unit_price": 500},
                  {"description": "Dressing", "item_type": "Procedure", "unit_price": 100}],
    })
    assert r.status_code == 201
    bill = admin.get(f"/api/bills/{r.get_json()['bill_id']}").get_json()
    assert (bill["subtotal"], bill["discount"], bill["tax"], bill["total_amount"]) == (1100, 100, 100, 1100)


def test_payments(admin):
    bill_id = admin.post("/api/bills", json={
        "patient_id": 4, "items": [{"description": "Consultation", "unit_price": 1000}]}).get_json()["bill_id"]
    pay = {"bill_id": bill_id, "payment_method": "UPI"}

    assert admin.post("/api/payments", json={**pay, "amount": 1500}).status_code == 400  # more than owed
    assert admin.post("/api/payments", json={**pay, "amount": 400}).get_json()["status"] == "Partial"
    assert admin.post("/api/payments", json={**pay, "amount": 600}).get_json()["status"] == "Paid"
    assert admin.post("/api/payments", json={**pay, "amount": 1}).status_code == 400   # already paid


# Staff, rooms, dashboard
def test_new_doctor_with_login(admin, client):
    r = admin.post("/api/staff", json={
        "first_name": "New", "last_name": "Doctor", "role": "Doctor", "email": "new.doc@hospital.com",
        "hire_date": date.today().isoformat(), "specialization": "ENT", "license_number": "MCI-ENT-099",
        "available_days": ["Mon", "Thu"], "create_login": True,
    })
    assert r.status_code == 201
    one_time = r.get_json()["temporary_password"]
    doctor = next(d for d in admin.get("/api/doctors").get_json() if d["license_number"] == "MCI-ENT-099")
    assert doctor["available_days"] == "Mon,Thu"

    # The same email can't be used twice
    r = admin.post("/api/staff", json={"first_name": "A", "last_name": "B", "role": "Nurse",
                                       "email": "new.doc@hospital.com", "hire_date": "2026-01-01"})
    assert r.status_code == 409

    admin.post("/api/auth/logout", json={})
    me = login(client, "New Doctor", one_time).get("/api/auth/me").get_json()
    assert me["role"] == "Doctor" and me["doctor_id"] == doctor["doctor_id"]
    assert me["must_change_password"] is True


def test_room_status_rules(admin):
    room = free_room(admin)
    url = f"/api/rooms/{room['room_id']}/status"
    assert admin.put(url, json={"status": "Under Maintenance"}).status_code == 200
    assert admin.put(url, json={"status": "Occupied"}).status_code == 400  # only admissions do that
    assert admin.put(url, json={"status": "Available"}).status_code == 200
    assert admin.put("/api/rooms/2/status", json={"status": "Available"}).status_code == 409  # patient inside


def test_dashboard_and_charts(admin):
    d = admin.get("/api/dashboard").get_json()
    assert d["total_patients"] >= 10 and d["admitted"] >= 3
    charts = admin.get("/api/dashboard/charts").get_json()
    assert len(charts["revenue"]) == 6
    assert admin.get("/api/alerts").status_code == 200
