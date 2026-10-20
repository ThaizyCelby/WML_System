# LendFlow Phase 1

Secure Django foundation for a digital lending / financial management platform.

Log in as:

Demo staff: demo.staff@demo.wethuml.local / SimWethu#2026!

Good client: demo001@demo.wethuml.local / SimWethu#2026!

Paid loan client: demo010@demo.wethuml.local / SimWethu#2026!

## Scope
- Custom User model
- RBAC role foundation
- Vendor/tenant foundation
- Session authentication endpoints
- Argon2 password hashing
- Django Axes: 3 failed attempts + 20-minute cooloff baseline
- Security events and temporary IP blocks
- Audit log foundation
- Redis-backed caching and DRF throttling
- PostgreSQL/Redis/Celery Docker architecture
- Health/readiness endpoints
- AI provider interfaces for OpenAI/Gemini/GLM
- Configurable 30% annual interest baseline

## Run locally
1. `python -m venv .venv`
2. Activate the environment.
3. `pip install -r requirements/development.txt`
4. Copy `.env.example` to `.env` and set `DJANGO_SECRET_KEY`.
5. `python manage.py makemigrations`
6. `python manage.py migrate`
7. `python manage.py createsuperuser`
8. `python manage.py runserver`

## Security note
This is Phase 1, not a declaration of production compliance. Before handling real financial/identity information, complete external provider security review, penetration testing, privacy/compliance review, secret management, encrypted object storage, backup/restore validation, and infrastructure hardening.
