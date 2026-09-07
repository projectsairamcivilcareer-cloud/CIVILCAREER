"""Railway production entry point for CIVIL CAREER."""

from app import app, create_database

# Ensure SQLite tables/columns exist before Gunicorn starts serving requests.
create_database()
