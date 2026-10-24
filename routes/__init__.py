"""All API routes, grouped by hospital module."""
from . import (admissions, appointments, billing, dashboard, patients, pharmacy, portal,
               settings, staff, wards)


def register_blueprints(app):
    for module in (dashboard, patients, staff, appointments, admissions, pharmacy, billing, wards,
                   portal, settings):
        app.register_blueprint(module.bp)
