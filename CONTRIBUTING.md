# Contributing

Thanks for taking an interest. Bug reports, ideas and pull requests are all welcome.

## Setting up

Follow the "Without Docker" steps in the [README](README.md#without-docker), then install the development tools:

```bash
pip install -r requirements-dev.txt
```

## Before opening a pull request

```bash
ruff check .     # style and common mistakes
pytest           # needs MySQL running; uses its own hospital_db_test database
```

Both run automatically on every pull request, along with a Docker build.

## Conventions

- Branch from `main` and name branches by type, for example `feat/lab-results` or `fix/slot-timezone`.
- Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `test:`, `ci:`, `build:`, `refactor:`.
- New API routes declare their permission with `@requires(...)` and get a test, including one for a role that must be refused.
- Anything a user types is shown with the `html` template helper in `static/js/core.js`, never by building HTML strings by hand.
- Keep pull requests focused on one change and describe how you tested it.
