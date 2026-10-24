"""
Database helpers.

Each request gets one MySQL connection, which is closed automatically
when the request finishes, so routes never have to call db.close().
"""
from contextlib import contextmanager
from pathlib import Path

import pymysql
import pymysql.cursors
from pymysql.constants import CLIENT
from flask import current_app, g

SCHEMA_FILE = Path(__file__).parent / "database" / "schema.sql"


def _connect(config, database=True, **extra):
    return pymysql.connect(
        host=config["DB_HOST"],
        port=config["DB_PORT"],
        user=config["DB_USER"],
        password=config["DB_PASSWORD"],
        database=config["DB_NAME"] if database else None,
        cursorclass=pymysql.cursors.DictCursor,
        charset="utf8mb4",
        **extra,
    )


def get_db():
    """The connection for the current request (opened on first use)."""
    if "db" not in g:
        g.db = _connect(current_app.config)
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)


def query(sql, params=None):
    """Run a SELECT and return all rows as a list of dicts."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(sql, params=None):
    """Run a SELECT and return the first row (or None)."""
    with get_db().cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()


@contextmanager
def transaction():
    """
    Group several writes together. Everything is saved at the end,
    or nothing is saved if any step fails.

        with transaction() as cur:
            cur.execute(...)
            cur.execute(...)
    """
    db = get_db()
    try:
        with db.cursor() as cur:
            yield cur
        db.commit()
    except Exception:
        db.rollback()
        raise


def load_schema(config):
    """
    Create the database from database/schema.sql.
    WARNING: this deletes the existing database with the same name.
    """
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    # The file is written for "hospital_db"; use whatever name is configured.
    sql = sql.replace("hospital_db", config["DB_NAME"])
    conn = _connect(config, database=False, client_flag=CLIENT.MULTI_STATEMENTS)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            while cur.nextset():
                pass
        conn.commit()
    finally:
        conn.close()


def drop_database(config):
    conn = _connect(config, database=False)
    try:
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{config['DB_NAME']}`")
    finally:
        conn.close()
