from datetime import date

from conftest import login


def test_role_must_match_the_account(client):
    r = client.post("/api/auth/login", json={"username": "doctor", "password": "doctor123", "role": "Admin"})
    assert r.status_code == 403
    assert "not an Admin account" in r.get_json()["error"]
    r = client.post("/api/auth/login", json={"username": "doctor", "password": "doctor123", "role": "Doctor"})
    assert r.status_code == 200


def test_each_role_only_sees_its_own_pages(client):
    login(client, "pharmacist")
    for url in ("/api/bills", "/api/staff", "/api/activity", "/api/appointments", "/api/wards"):
        assert client.get(url).status_code == 403, url
    assert client.get("/api/medicines").status_code == 200
    assert "monthly_revenue" not in client.get("/api/dashboard").get_json()

    client.post("/api/auth/logout", json={})
    login(client, "reception")
    assert client.get("/api/bills").status_code == 200
    assert client.get("/api/prescriptions").status_code == 403
    patient = client.get("/api/patients/1").get_json()
    assert patient["prescriptions"] is None and patient["bills"] is not None


def make_user(admin, username, password):
    r = admin.post("/api/staff", json={
        "first_name": "Temp", "last_name": username, "role": "Nurse", "email": f"{username}@hospital.com",
        "hire_date": date.today().isoformat(), "username": username, "password": password,
    })
    assert r.status_code == 201, r.get_json()


def test_account_locks_after_five_wrong_passwords(admin, app):
    make_user(admin, "locktest", "right-pass-1")
    other = app.test_client()
    for _ in range(4):
        assert other.post("/api/auth/login", json={"username": "locktest", "password": "nope"}).status_code == 401
    assert other.post("/api/auth/login", json={"username": "locktest", "password": "nope"}).status_code == 429
    # Even the right password is refused while locked
    assert other.post("/api/auth/login", json={"username": "locktest", "password": "right-pass-1"}).status_code == 429


def test_change_password(admin, app):
    make_user(admin, "pwtest", "first-pass-1")
    user = login(app.test_client(), "pwtest", "first-pass-1")
    change = {"current_password": "wrong-one-1", "new_password": "second-pass-2"}
    assert user.post("/api/auth/change-password", json=change).status_code == 400
    assert user.post("/api/auth/change-password", json={**change, "new_password": "short"}).status_code == 400
    change["current_password"] = "first-pass-1"
    assert user.post("/api/auth/change-password", json=change).status_code == 200
    login(app.test_client(), "pwtest", "second-pass-2")


def test_activity_log_records_changes(admin):
    assert admin.put("/api/medicines/1/restock", json={"quantity": 5}).status_code == 200
    log = admin.get("/api/activity?search=Restocked").get_json()
    assert log and log[0]["actor_role"] == "Admin" and log[0]["details"] == "M-001 +5"
