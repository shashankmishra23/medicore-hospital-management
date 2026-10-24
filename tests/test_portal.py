from datetime import date, timedelta

from conftest import login, patient_login

NEW = {
    "first_name": "Riya", "last_name": "Verma", "dob": "1996-04-12", "gender": "Female",
    "phone": "9123456780", "email": "riya@example.com", "password": "riya2026pass",
}


def next_day(weekdays, after=1):
    d = date.today() + timedelta(days=after)
    while d.weekday() not in weekdays:
        d += timedelta(days=1)
    return d.isoformat()


def test_register_and_sign_in(app):
    c = app.test_client()
    assert c.post("/api/portal/register", json={**NEW, "password": "weak"}).status_code == 400
    r = c.post("/api/portal/register", json=NEW)
    assert r.status_code == 201
    me = c.get("/api/portal/me").get_json()
    assert me["first_name"] == "Riya" and me["upcoming"] == []

    assert app.test_client().post("/api/portal/register", json=NEW).status_code == 409   # same email
    patient_login(app.test_client(), "RIYA@example.com", NEW["password"])                # email is not case-sensitive


def test_patients_and_staff_are_kept_apart(app):
    patient = patient_login(app.test_client())
    assert patient.get("/api/patients").status_code == 401
    assert patient.get("/api/auth/me").status_code == 401

    staff = login(app.test_client(), "admin")
    assert staff.get("/api/portal/me").status_code == 401


def test_online_booking(app):
    c = patient_login(app.test_client())
    day = next_day({0, 2, 4})  # Dr. Priya Mehta works Mon, Wed, Fri
    slots = c.get(f"/api/portal/slots?doctor_id=2&date={day}").get_json()
    assert slots[0] == {"time": "09:00", "available": True}

    r = c.post("/api/portal/appointments", json={"doctor_id": 2, "appointment_date": day, "appointment_time": "09:00"})
    assert r.status_code == 201
    aid = r.get_json()["appointment_id"]
    slots = c.get(f"/api/portal/slots?doctor_id=2&date={day}").get_json()
    assert slots[0]["available"] is False

    # One visit per doctor per day, and taken or made-up times are refused
    again = {"doctor_id": 2, "appointment_date": day, "appointment_time": "10:00"}
    assert c.post("/api/portal/appointments", json=again).status_code == 409
    other = patient_login(app.test_client(), NEW["email"], NEW["password"])
    taken = {**again, "appointment_time": "09:00"}
    assert other.post("/api/portal/appointments", json=taken).status_code == 409
    assert other.post("/api/portal/appointments", json={**again, "appointment_time": "09:10"}).status_code == 409

    # Staff see it marked as an online booking
    staff = login(app.test_client(), "reception")
    booked = [a for a in staff.get("/api/appointments?booked_via=Online").get_json() if a["appointment_id"] == aid]
    assert booked and booked[0]["patient_name"] == "Anita Patel"

    # Only the owner can cancel
    assert other.post(f"/api/portal/appointments/{aid}/cancel", json={}).status_code == 404
    assert c.post(f"/api/portal/appointments/{aid}/cancel", json={}).status_code == 200
    assert c.post(f"/api/portal/appointments/{aid}/cancel", json={}).status_code == 409


def test_booking_rules(app):
    c = patient_login(app.test_client())
    sunday = next_day({6})
    assert c.get(f"/api/portal/slots?doctor_id=2&date={sunday}").status_code == 400
    far = (date.today() + timedelta(days=60)).isoformat()
    assert c.get(f"/api/portal/slots?doctor_id=2&date={far}").status_code == 400


def test_patient_only_sees_own_records(app):
    c = patient_login(app.test_client())   # Anita Patel, patient 2
    assert c.get("/api/portal/bills/1").status_code == 404        # bill 1 belongs to patient 1
    assert all(b["bill_id"] != 1 for b in c.get("/api/portal/bills").get_json())
    rx = c.get("/api/portal/prescriptions").get_json()
    assert rx and all(len(r["items"]) > 0 for r in rx)


def test_reception_gives_portal_access(app):
    staff = login(app.test_client(), "reception")
    r = staff.post("/api/patients/5/portal-access", json={"email": "amit.s@email.com"})
    assert r.status_code == 201
    temp = r.get_json()["temporary_password"]
    assert staff.post("/api/patients/5/portal-access", json={"email": "x@y.com"}).status_code == 409

    me = patient_login(app.test_client(), "amit.s@email.com", temp).get("/api/portal/me").get_json()
    assert me["patient_id"] == 5


def test_update_profile(app):
    c = patient_login(app.test_client())
    r = c.put("/api/portal/profile", json={"phone": "9822222222", "allergies": "Dust", "blood_group": "A+"})
    assert r.status_code == 200
    assert c.get("/api/portal/me").get_json()["allergies"] == "Dust"
