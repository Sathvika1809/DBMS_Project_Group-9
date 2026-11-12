import os

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "papertrading")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")

CONN_STRING = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Rows come back as dicts. Leaving the `with pool.connection()` block commits;
# an exception inside it rolls back, which is what makes settlement atomic.
pool = ConnectionPool(
    conninfo=CONN_STRING,
    min_size=1,
    max_size=int(os.getenv("DB_POOL_MAX", "20")),
    kwargs={"row_factory": dict_row},
    open=False,
)


def get_db_connection():
    """Context manager: `with get_db_connection() as conn:`"""
    return pool.connection()


def db_error_message(exc: Exception) -> str:
    """The message the database raised (e.g. from RAISE EXCEPTION), without driver noise."""
    if isinstance(exc, psycopg.Error) and exc.diag and exc.diag.message_primary:
        return exc.diag.message_primary
    return str(exc)
