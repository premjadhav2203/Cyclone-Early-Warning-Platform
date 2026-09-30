
import psycopg2
from psycopg2.extras import execute_values, Json
from contextlib import contextmanager
from src.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD


@contextmanager
def get_conn():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_pilot_region_id(cur, name: str):
    cur.execute("SELECT id FROM pilot_regions WHERE name = %s", (name,))
    row = cur.fetchone()
    if row is None:
        raise ValueError(
            f"Pilot region '{name}' not found — did you run db/schema.sql "
            f"(it seeds the default region)?"
        )
    return row[0]


def bulk_insert(cur, table: str, columns: list, rows: list, page_size: int = 500):
    """Generic bulk insert helper using execute_values for speed."""
    if not rows:
        return
    col_str = ", ".join(columns)
    query = f"INSERT INTO {table} ({col_str}) VALUES %s"
    execute_values(cur, query, rows, page_size=page_size)
