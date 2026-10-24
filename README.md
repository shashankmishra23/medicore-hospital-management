# MediCore HMS

A hospital management system built with Flask and MySQL. It has two sides:

- a **staff app** where admins, doctors, nurses, pharmacists and receptionists each sign in with their own role and only see the parts of the hospital they work in, and
- a **patient portal** where patients sign up, book appointments online and see their prescriptions and bills.

The hospital name, address and phone number come from settings, so the same code can be set up for any hospital.

![Staff dashboard](docs/screenshots/dashboard.jpg)

## Features

**Staff app**

- Role-based sign in. Staff pick their role (Admin, Doctor, Nurse, Pharmacist, Receptionist), then type their name and password. The server checks that the account really has that role.
- No usernames to remember: staff sign in with their full name or first name. New staff get a one-time password from the admin and choose their own the first time they sign in. Admins can reset a forgotten password.
- Each role gets its own menu and data. For example, a pharmacist can't open billing, and a doctor doesn't see revenue. This is enforced by the API, not just hidden in the UI.
- Patients: register, edit, search by name / phone / ID, full patient file with history, allergies, admissions, prescriptions and bills.
- Appointments: book from the doctor's free 30-minute slots, with checks for working days, past dates and double-booking. Online bookings are marked so reception can spot them.
- Admissions: admit to a free room, discharge, and create the discharge bill automatically (room days, doctor's fee, medicines given during the stay).
- Prescriptions: doctors prescribe, the pharmacy dispenses, stock goes down. Expired or out-of-stock medicine can't be dispensed.
- Pharmacy stock with low-stock and expiry alerts, billing with discounts, tax and part payments, printable receipts.
- Wards and rooms view showing who is in which room.
- Activity log (admin only): every sign-in and change, with who did it and when.

**Patient portal**

- Sign up with email and password, or get access from reception if you already have a hospital record.
- Book an appointment in four steps: doctor, day, time slot, reason. Cancel upcoming visits.
- See prescriptions (and print them), bills and receipts, and keep contact details and allergies up to date.

**Security**

- Passwords are stored as salted hashes. Accounts lock for 15 minutes after 5 wrong passwords.
- One-time passwords must be replaced before anything else can be done. New passwords need letters and numbers.
- SQL queries are parameterised; all text shown on the page is escaped; API writes must be JSON (blocks cross-site form posts).
- Database password and secret key live in `.env`, which is not committed.

## Screenshots

| Sign in | Patient portal |
|---|---|
| ![Login](docs/screenshots/login.jpg) | ![Portal home](docs/screenshots/portal-home.jpg) |
| **Online booking** | **Appointments (staff)** |
| ![Booking](docs/screenshots/portal-booking.jpg) | ![Appointments](docs/screenshots/appointments.jpg) |
| **Patient file** | **Activity log** |
| ![Patient file](docs/screenshots/patient-file.jpg) | ![Activity log](docs/screenshots/activity-log.jpg) |

## Tech stack

- Python 3, Flask (blueprints, app factory), PyMySQL
- MySQL 8 (foreign keys, views, generated columns, row locking in transactions)
- HTML, CSS and plain JavaScript, Chart.js for the dashboard charts
- pytest, with GitHub Actions running the tests against MySQL on every push

## Running it locally

You need Python 3.10+ and MySQL 8.

```bash
git clone https://github.com/<your-username>/medicore-hospital-management.git
cd medicore-hospital-management
python -m venv .venv
.venv\Scripts\activate            # macOS / Linux: source .venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and set at least `DB_PASSWORD` and `SECRET_KEY`. The `HOSPITAL_*` values change the name and contact details shown in the app.

Create the database with sample data, then start the server:

```bash
flask init-db       # warning: drops and recreates the hospital_db database
python app.py
```

Open http://127.0.0.1:5000.

### Signing in

Choose your role on the login page, then type your **name** (for example `Shashank Mishra`, or just `Shashank`) and password.

The sample data has one person for each role:

| Role | Name | Password |
|---|---|---|
| Admin | Shashank Mishra | `admin123` |
| Doctor | Arun Sharma | `doctor123` |
| Nurse | Sunita Singh | `nurse123` |
| Pharmacist | Mohit Jain | `pharma123` |
| Receptionist | Kavita Rao | `reception123` |
| Patient (portal) | `anita.p@email.com` | `patient123` |

**Demo mode.** Set `DEMO_MODE=1` in `.env` and any password is accepted, which is handy when showing the project to someone. The login page says when it is on. Keep it `0` for real use.

New staff are added from **Doctors & Staff → Add Staff**. The admin gets a one-time password to hand over, and the person picks their own password the first time they sign in.

### What each role can do

| | Admin | Doctor | Nurse | Pharmacist | Receptionist |
|---|:-:|:-:|:-:|:-:|:-:|
| Patients | edit | edit | edit | view | edit |
| Appointments | edit | edit | view | | edit |
| Admissions | edit | edit | edit | | view |
| Prescriptions | edit | write | view | dispense | |
| Pharmacy stock | edit | view | | edit | |
| Billing | edit | | | | edit |
| Wards & rooms | edit | view | edit | | view |
| Staff | edit | | | | view |
| Activity log | view | | | | |

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a separate `hospital_db_test` database that they create and delete themselves.

## Project layout

```
app.py              app factory and CLI commands (init-db, create-user)
config.py           settings from .env, including hospital branding
auth.py             staff login, roles and permissions, password changes, lockout
audit.py            activity log
db.py, utils.py     database helpers, input validation, error handling
routes/             API, one module per area (patients, appointments, portal, ...)
templates/          login.html, index.html (staff app), portal.html (patients)
static/js/          core.js (shared helpers) plus one file per page
static/css/         styles, dark and light theme
database/schema.sql tables, views and sample data
tests/              pytest suite
```

## License

MIT, see [LICENSE](LICENSE). Made by Shashank Mishra.
