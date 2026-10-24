"""All API routes, grouped by hospital module."""
from . import admissions, appointments, billing, dashboard, patients, pharmacy, portal, staff, wards


def register_blueprints(app):
    for module in (dashboard, patients, staff, appointments, admissions, pharmacy, billing, wards, portal):
        app.register_blueprint(module.bp)
