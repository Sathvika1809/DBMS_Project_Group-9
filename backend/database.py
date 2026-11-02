import os
from psycopg_pool import ConnectionPool

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "papertrading")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "postgrespassword")

CONN_STRING = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Initialize connection pool
pool = ConnectionPool(conninfo=CONN_STRING, min_size=1, max_size=10, open=False)

def get_db_connection():
    """Context manager helper for acquiring database connections."""
    return pool.connection()