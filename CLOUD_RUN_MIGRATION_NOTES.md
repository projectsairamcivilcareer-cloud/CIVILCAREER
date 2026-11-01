# CIVIL CAREER migration notes — Cloud Run + Neon + Supabase Storage

## Safety status

- This work is isolated on branch `migration/vercel-neon-audit`.
- The `main` branch has not been changed.
- No Railway service, PostgreSQL volume, or student data has been modified.
- No new cloud resources have been provisioned.
- Do not deploy until the production database has been recovered/exported and the session/storage blockers below are resolved.

## Proposed hosting

- Backend: Google Cloud Run, Mumbai region (`asia-south1`), running the existing Flask application in a container.
- Database: Neon PostgreSQL. Keep the existing `psycopg` database layer; do not convert to MongoDB or SQLite.
- Object storage: Supabase Storage for durable uploaded files where needed. Existing profile-photo BYTEA values in PostgreSQL should remain readable until a verified copy to Storage is completed.
- GitHub: continue using the existing repository as source control and deployment source.
- GitHub Pages: optional for static-only public content. The existing application has Flask/Jinja routes and authenticated workflows, so Pages cannot host the current app unchanged. Cloud Run should serve the existing Flask routes unless a separate frontend conversion is explicitly planned.

## Findings from current source

- `app.py` defines the Flask application and uses PostgreSQL through `psycopg`.
- The application currently configures Flask-Session with filesystem storage. This is not durable/shared across Cloud Run instances or restarts; move sessions to PostgreSQL (or another durable shared session store) before production deployment.
- The application stores current profile-photo bytes in the PostgreSQL `students.profile_photo_data` BYTEA column and has a filesystem fallback.
- `railway_start.py` calls `create_database()` and starts a persistent background job-sync thread. Do not reuse that entry point on Cloud Run.
- `create_database()` contains schema setup and legacy SQLite migration logic. It must not run automatically on every Cloud Run startup. Schema creation/import should be a controlled, one-time reviewed migration.
- Mock-test state, PDF generation, account/login, history and job routes are part of the existing Flask app and must be regression-tested after migration.

## Required sequence

1. Recover/export the Railway PostgreSQL data without deleting its attached volume.
2. Inspect and securely back up the public repository's tracked `civilcareer.db`; do not assume it contains the production database.
3. Create a Neon PostgreSQL project and import the verified PostgreSQL backup; compare table/row counts and sample records before switching traffic.
4. Create Supabase Storage buckets and migrate only verified file assets; preserve existing database photo bytes until checks pass.
5. Implement durable server-side sessions and Supabase Storage integration with backwards-compatible reads.
6. Add scheduled job sync as a separate scheduled task; remove the always-running thread from the Cloud Run entry point.
7. Deploy a test Cloud Run service in Mumbai, verify login, registration, profile, mock-test timer/answers, history/detail/PDF, jobs, email, and mobile/desktop pages.
8. Configure custom domain/HTTPS, monitor usage and billing, then switch traffic only after explicit approval.

## Cloud Run billing note

Cloud Run has a monthly free usage tier, but Google Cloud requires billing to be enabled. Usage beyond free allowances and related products (for example image storage/build services and network egress) can incur charges. Configure budget alerts before deploying; alerts are not a hard spending cap.

## Current blockers

- Railway PostgreSQL is offline; the production backup is not yet available.
- A new Neon database must not be populated from the old SQLite file without verifying its contents and age.
- Persistent session storage has not yet been implemented.
- Supabase Storage project/buckets have not yet been created.
- Google Cloud billing/project access has not yet been confirmed.
- The public GitHub repository contains a tracked `civilcareer.db` file (65,536 bytes). Its contents have not been inspected. Treat it as potentially sensitive until safely checked; removing a current copy alone does not erase Git history.
