# Changelog

All notable changes to this project are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [semantic versioning](https://semver.org/).

## [1.0.1] - 2026-10-25

### Changed

- The sample hospital is now in Gomti Nagar, Lucknow (address, phone and department numbers), and the sample patients live in Lucknow.
- README screenshots retaken with the new address and a new sample patient.

## [1.0.0] - 2026-10-25

First public release.

### Added

- Staff app with role-based access for Admin, Doctor, Nurse, Pharmacist and Receptionist, enforced by the API.
- Sign-in by name, with an admin switch for whether a password is required.
- Settings page for creating staff and patient accounts, setting passwords and turning accounts off.
- Patient portal: sign-up, online booking from free time slots, cancellations, prescriptions, bills and receipts.
- Patients, appointments, admissions with automatic discharge bills, prescriptions and dispensing, pharmacy stock, billing and payments, wards and rooms.
- Dashboard with charts and an alerts bell, filtered by role.
- Activity log of sign-ins and changes.
- Account lockout after repeated wrong passwords.
- Hospital branding through environment settings.
- Docker setup and a `/health` endpoint.
- Test suite (40 tests) and CI with lint, tests against MySQL 8 and a Docker smoke test.

[1.0.1]: https://github.com/shashankmishra23/medicore-hospital-management/releases/tag/v1.0.1
[1.0.0]: https://github.com/shashankmishra23/medicore-hospital-management/releases/tag/v1.0.0
