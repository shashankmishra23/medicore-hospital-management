from datetime import date

from app import create_app
from conftest import TEST_DB, login


def staff_login(client, name, password, role=None):
    return client.post("/api/auth/login", json={"name": name, "password": password, "role": role})


def test_sign_in_with_full_name_first_name_or_username(app):
    for name in ("Arun Sharma", "arun", "ARUN SHARMA", "arun.sharma", "  Arun   Sharma "):
        r = staff_login(app.test_client(), name, "doctor123")
        assert r.status_code == 200, name
        assert r.get_json()["name"] == "Arun Sharma"


def test_role_must_match_the_account(client):
    r = staff_login(client, "Arun Sharma", "doctor123", "Admin")
    assert r.status_code == 403
    assert "does not have an Admin account" in r.get_json()["error"]
    assert staff_login(client, "Arun Sharma", "doctor123", "Doctor").status_code == 200


def add_staff(admin, first, last, role="Nurse"):
    r = admin.post("/api/staff", json={
        "first_name": first, "last_name": last, "role": role, "email": f"{first}.{last}@hospital.com".lower(),
        "hire_date": date.today().isoformat(), "create_login": True,
    })
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def test_same_first_name_needs_full_name(admin, app):
    one_time = add_staff(admin, "Arun", "Kapoor")["temporary_password"]
    r = staff_login(app.test_client(), "Arun", one_time)
    assert r.status_code == 409 and "full name" in r.get_json()["error"]
    # Picking the role is enough to tell them apart
    assert staff_login(app.test_client(), "Arun", one_time, "Nurse").status_code == 200


def test_first_sign_in_requires_own_password(admin, app):
    one_time = add_staff(admin, "Meena", "Joshi")["temporary_password"]
    user = app.test_client()
    me = staff_login(user, "Meena Joshi", one_time).get_json()
    assert me["must_change_password"] is True
    assert user.get("/api/patients").status_code == 403          # blocked until a new password is set

    change = {"current_password": one_time, "new_password": "meena-pass-7"}
    assert user.post("/api/auth/change-password", json=change).status_code == 200
    assert user.get("/api/patients").status_code == 200
    assert staff_login(app.test_client(), "Meena Joshi", "meena-pass-7").get_json()["must_change_password"] is False


def test_admin_resets_a_forgotten_password(admin, app):
    staff_id = add_staff(admin, "Ravi", "Kumar")["staff_id"]
    r = admin.post(f"/api/staff/{staff_id}/reset-password", json={})
    assert r.status_code == 200
    assert staff_login(app.test_client(), "Ravi Kumar", r.get_json()["temporary_password"]).status_code == 200


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


def test_account_locks_after_five_wrong_passwords(admin, app):
    one_time = add_staff(admin, "Lock", "Test")["temporary_password"]
    other = app.test_client()
    for _ in range(4):
        assert staff_login(other, "Lock Test", "nope").status_code == 401
    assert staff_login(other, "Lock Test", "nope").status_code == 429
    # Even the right password is refused while locked
    assert staff_login(other, "Lock Test", one_time).status_code == 429


def test_demo_mode_accepts_any_password(app):
    demo = create_app({"DB_NAME": TEST_DB, "TESTING": True, "SECRET_KEY": "test", "DEMO_MODE": True})
    c = demo.test_client()
    assert staff_login(c, "Shashank", "anything at all", "Admin").status_code == 200
    assert staff_login(c, "Nobody Here", "anything").status_code == 401   # the person must still exist
    assert b"Demo mode is on" in demo.test_client().get("/login").data
    assert b"Demo mode is on" not in app.test_client().get("/login").data


def test_change_password(admin, app):
    user = login(app.test_client(), "nurse")
    change = {"current_password": "wrong-one-1", "new_password": "second-pass-2"}
    assert user.post("/api/auth/change-password", json=change).status_code == 400
    assert user.post("/api/auth/change-password", json={**change, "new_password": "short"}).status_code == 400
    change["current_password"] = "nurse123"
    assert user.post("/api/auth/change-password", json=change).status_code == 200
    login(app.test_client(), "Sunita Singh", "second-pass-2")


def test_activity_log_records_changes(admin):
    assert admin.put("/api/medicines/1/restock", json={"quantity": 5}).status_code == 200
    log = admin.get("/api/activity?search=Restocked").get_json()
    assert log and log[0]["actor_role"] == "Admin" and log[0]["details"] == "M-001 +5"
