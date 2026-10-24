"""
MediCore Hospital Management System
Flask backend with MySQL.

Run:  python app.py      then open http://127.0.0.1:5000

Extra commands (run in this folder):
  flask init-db       create the database with sample data (deletes the old one!)
  flask create-user   add a login for an existing staff member
"""
import click
from flask import Flask
from werkzeug.security import generate_password_hash

import auth
import db
from config import Config
from routes import register_blueprints
from utils import JSONProvider, register_error_handlers


def create_app(config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if config:
        app.config.update(config)
    app.json = JSONProvider(app)

    db.init_app(app)
    auth.init_app(app)
    register_blueprints(app)
    register_error_handlers(app)
    register_commands(app)

    @app.get("/health")
    def health():
        """For Docker and uptime monitors: is the app up, and can it reach the database?"""
        try:
            db.query_one("SELECT 1")
        except Exception:
            app.logger.exception("Health check: database unreachable")
            return {"status": "error", "database": "unreachable"}, 503
        return {"status": "ok", "database": "ok"}

    return app


def register_commands(app):
    @app.cli.command("init-db")
    @click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
    def init_db(yes):
        """Create the database from database/schema.sql (with sample data)."""
        name = app.config["DB_NAME"]
        if not yes:
            click.confirm(f"This deletes the database '{name}' and all its data, then "
                          f"creates it again with sample data. Continue?", abort=True)
        db.load_schema(app.config)
        click.echo(f"Database '{name}' is ready. Sign in as Admin: Shashank Mishra / admin123.")

    @app.cli.command("create-user")
    @click.option("--staff-id", type=int, required=True, prompt="Staff ID", help="Existing staff_id.")
    @click.option("--username", required=True, prompt=True)
    @click.option("--role", required=True, prompt=True,
                  type=click.Choice(["Admin", "Doctor", "Nurse", "Pharmacist", "Receptionist"]))
    @click.password_option()
    def create_user(staff_id, username, role, password):
        """Give an existing staff member a login."""
        if len(password) < 8 or password.isalpha() or password.isdigit():
            raise click.BadParameter("must be at least 8 characters with letters and numbers",
                                     param_hint="password")
        with app.app_context():
            with db.transaction() as cur:
                cur.execute("""
                    INSERT INTO system_users (staff_id, username, password_hash, role)
                    VALUES (%s, %s, %s, %s)
                """, (staff_id, username, generate_password_hash(password), role))
        click.echo(f"User '{username}' created.")


app = create_app()

if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], port=app.config["PORT"])
