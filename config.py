"""
App settings, read from environment variables.

Put your own values in a file called .env (copy .env.example).
The .env file is listed in .gitignore, so your password never goes to GitHub.
"""
import os
import secrets
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    # Used to sign the login cookie. If it is not set, a random one is made,
    # which means everyone gets logged out when the server restarts.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "root")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "hospital_db")

    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"
    PORT = int(os.environ.get("PORT", "5000"))

    # Your hospital's details. Change these to rebrand the whole app:
    # login page, sidebar, receipts and printed prescriptions.
    HOSPITAL = {
        "name": os.environ.get("HOSPITAL_NAME", "MediCore Hospital"),
        "tagline": os.environ.get("HOSPITAL_TAGLINE", "Modern care, one click away"),
        "phone": os.environ.get("HOSPITAL_PHONE", "+91 512 300 100"),
        "email": os.environ.get("HOSPITAL_EMAIL", "care@medicore.example"),
        "address": os.environ.get("HOSPITAL_ADDRESS", "Civil Lines, Kanpur, Uttar Pradesh"),
    }

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
