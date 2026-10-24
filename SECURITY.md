# Security policy

## Reporting a vulnerability

Please don't open a public issue for security problems. Report them privately through
[GitHub's security advisory form](https://github.com/shashankmishra23/medicore-hospital-management/security/advisories/new)
with steps to reproduce, and I'll reply as soon as I can.

## Before using this in a real hospital

- Change or remove the sample accounts that come with the sample data.
- Keep **Ask for a password when signing in** switched on (Settings page).
- Set a long random `SECRET_KEY` and a strong database password in `.env`.
- Serve the app over HTTPS behind a production server (the Docker image uses gunicorn).
