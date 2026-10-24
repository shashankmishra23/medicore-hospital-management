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

from app import create_app  # noqa: E402
import db  # noqa: E402

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


DEMO_PASSWORDS = {
    "admin": "admin123", "doctor": "doctor123", "nurse": "nurse123",
    "pharmacist": "pharma123", "reception": "reception123",
}


def login(client, username, password=None):
    password = password or DEMO_PASSWORDS[username]
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    return client


def patient_login(client, email="anita.p@email.com", password="patient123"):
    r = client.post("/api/portal/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return client


@pytest.fixture
def admin(client):
    return login(client, "admin")
