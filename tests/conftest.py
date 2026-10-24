"""
Test setup.

The tests use their OWN database (hospital_db_test by default), which is
deleted and created again from database/schema.sql, so your real data is
never touched. MySQL settings come from your .env file.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from app import create_app  # noqa: E402

TEST_DB = os.environ.get("TEST_DB_NAME", "hospital_db_test")


@pytest.fixture(scope="session")
def app():
    app = create_app({"DB_NAME": TEST_DB, "TESTING": True, "SECRET_KEY": "test"})
    db.load_schema(app.config)
    yield app
    db.drop_database(app.config)


@pytest.fixture
def client(app):
    return app.test_client()


# Sample staff accounts: role -> (name they sign in with, password)
DEMO_STAFF = {
    "admin": ("Shashank Mishra", "admin123"),
    "doctor": ("Arun Sharma", "doctor123"),
    "nurse": ("Sunita Singh", "nurse123"),
    "pharmacist": ("Mohit Jain", "pharma123"),
    "reception": ("Kavita Rao", "reception123"),
}


def login(client, who, password=None):
    """who is a key of DEMO_STAFF, or any staff name (then pass the password)."""
    name, demo_password = DEMO_STAFF.get(who, (who, None))
    r = client.post("/api/auth/login", json={"name": name, "password": password or demo_password})
    assert r.status_code == 200, r.get_json()
    return client


def patient_login(client, email="anita.p@email.com", password="patient123"):
    r = client.post("/api/portal/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return client


@pytest.fixture
def admin(client):
    return login(client, "admin")
