from contextlib import contextmanager
from datetime import date

from conftest import login, patient_login


def staff_login(client, name, password=None, role=None):
    body = {"name": name, "role": role}
    if password is not None:
        body["password"] = password
    return client.post("/api/auth/login", json=body)


def add_staff_with_account(admin, first, last, password=None, role="Nurse"):
    """Add a staff member, then give them a login on the Settings page."""
    r = admin.post("/api/staff", json={
        "first_name": first, "last_name": last, "role": role, "email": f"{first}.{last}@hospital.com".lower(),
        "hire_date": date.today().isoformat(),
    })
    assert r.status_code == 201, r.get_json()
    staff_id = r.get_json()["staff_id"]
    r = admin.post("/api/settings/staff-accounts", json={"staff_id": staff_id, "role": role, "password": password})
    assert r.status_code == 201, r.get_json()
    account = next(s for s in admin.get("/api/settings/accounts").get_json()["staff"] if s["staff_id"] == staff_id)
    return account["user_id"]


@contextmanager
def passwords_switched_off(admin):
    assert admin.put("/api/settings", json={"require_password": False}).status_code == 200
    try:
        yield
    finally:
        admin.put("/api/settings", json={"require_password": True})


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


def test_same_first_name_needs_full_name(admin, app):
    add_staff_with_account(admin, "Arun", "Kapoor", "kapoor-pass-1")
    r = staff_login(app.test_client(), "Arun", "kapoor-pass-1")
    assert r.status_code == 409 and "full name" in r.get_json()["error"]
    # Picking the role is enough to tell them apart
    assert staff_login(app.test_client(), "Arun", "kapoor-pass-1", "Nurse").status_code == 200


def test_settings_page_is_admin_only(app):
    nurse = login(app.test_client(), "nurse")
    assert nurse.get("/api/settings").status_code == 403
    assert nurse.put("/api/settings", json={"require_password": False}).status_code == 403
    assert nurse.get("/api/settings/accounts").status_code == 403


def test_password_switch_off_and_on(admin, app):
    assert admin.get("/api/settings").get_json() == {"require_password": True}
    assert staff_login(app.test_client(), "Arun Sharma").status_code == 401           # password needed

    with passwords_switched_off(admin):
        r = staff_login(app.test_client(), "Arun Sharma", role="Doctor")                # name only
        assert r.status_code == 200 and r.get_json()["name"] == "Arun Sharma"
        assert staff_login(app.test_client(), "Nobody Here").status_code == 401        # must still exist
        r = app.test_client().post("/api/portal/login", json={"email": "anita.p@email.com"})
        assert r.status_code == 200                                                    # patients: email only
        assert b'id="password"' not in app.test_client().get("/login").data

    assert b'id="password"' in app.test_client().get("/login").data
    assert staff_login(app.test_client(), "Arun Sharma", "wrong").status_code == 401


def test_account_without_password_only_works_while_passwords_are_off(admin, app):
    user_id = add_staff_with_account(admin, "Nopass", "Person")
    assert staff_login(app.test_client(), "Nopass Person", "anything").status_code == 401
    with passwords_switched_off(admin):
        assert staff_login(app.test_client(), "Nopass Person").status_code == 200

    # The admin sets a password for them on the Settings page
    url = f"/api/settings/staff-accounts/{user_id}"
    assert admin.put(url, json={"password": "short"}).status_code == 400
    assert admin.put(url, json={"password": "nopass-now-1"}).status_code == 200
    assert staff_login(app.test_client(), "Nopass Person", "nopass-now-1").status_code == 200


def test_turning_an_account_off(admin, app):
    user_id = add_staff_with_account(admin, "Turn", "Off", "turn-off-pass-1")
    url = f"/api/settings/staff-accounts/{user_id}"
    assert admin.put(url, json={"is_active": False}).status_code == 200
    assert staff_login(app.test_client(), "Turn Off", "turn-off-pass-1").status_code == 403
    assert admin.put(url, json={"is_active": True}).status_code == 200
    assert staff_login(app.test_client(), "Turn Off", "turn-off-pass-1").status_code == 200

    me = admin.get("/api/auth/me").get_json()
    r = admin.put(f"/api/settings/staff-accounts/{me['user_id']}", json={"is_active": False})
    assert r.status_code == 400   # can't lock yourself out


def test_account_locks_after_five_wrong_passwords(admin, app):
    user_id = add_staff_with_account(admin, "Lock", "Test", "right-pass-1")
    other = app.test_client()
    for _ in range(4):
        assert staff_login(other, "Lock Test", "nope").status_code == 401
    assert staff_login(other, "Lock Test", "nope").status_code == 429
    # Even the right password is refused while locked...
    assert staff_login(other, "Lock Test", "right-pass-1").status_code == 429
    # ...until the admin sets a new one, which unlocks the account
    admin.put(f"/api/settings/staff-accounts/{user_id}", json={"password": "fresh-pass-2"})
    assert staff_login(other, "Lock Test", "fresh-pass-2").status_code == 200


def test_patient_sign_up_without_password_while_off(admin, app):
    new = {"first_name": "No", "last_name": "Password", "dob": "1990-01-01", "gender": "Male",
           "phone": "9000099999", "email": "nopw@example.com"}
    assert app.test_client().post("/api/portal/register", json=new).status_code == 400   # password needed
    with passwords_switched_off(admin):
        assert app.test_client().post("/api/portal/register", json=new).status_code == 201


def test_each_role_only_sees_its_own_pages(client):
    login(client, "pharmacist")
    for url in ("/api/bills", "/api/staff", "/api/activity", "/api/appointments", "/api/wards", "/api/settings"):
        assert client.get(url).status_code == 403, url
    assert client.get("/api/medicines").status_code == 200
    assert "monthly_revenue" not in client.get("/api/dashboard").get_json()

    client.post("/api/auth/logout", json={})
    login(client, "reception")
    assert client.get("/api/bills").status_code == 200
    assert client.get("/api/prescriptions").status_code == 403
    patient = client.get("/api/patients/1").get_json()
    assert patient["prescriptions"] is None and patient["bills"] is not None


def test_change_password(app):
    user = login(app.test_client(), "nurse")
    change = {"current_password": "wrong-one-1", "new_password": "second-pass-2"}
    assert user.post("/api/auth/change-password", json=change).status_code == 400
    assert user.post("/api/auth/change-password", json={**change, "new_password": "short"}).status_code == 400
    change["current_password"] = "nurse123"
    assert user.post("/api/auth/change-password", json=change).status_code == 200
    login(app.test_client(), "Sunita Singh", "second-pass-2")
    patient_login(app.test_client())


def test_activity_log_records_changes(admin):
    assert admin.put("/api/medicines/1/restock", json={"quantity": 5}).status_code == 200
    log = admin.get("/api/activity?search=Restocked").get_json()
    assert log and log[0]["actor_role"] == "Admin" and log[0]["details"] == "M-001 +5"
