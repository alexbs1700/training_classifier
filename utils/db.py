"""Run the ``.sql`` files in ``querys/`` against the DuckDB store (or straight at
data files).

``run_query("weekly_volume")`` reads ``querys/weekly_volume.sql``, executes it and
returns the final statement's result as a DataFrame.

The store at ``data/activities.db`` is attached as the catalog ``data``, so a
query can say ``FROM data.activities`` or just ``FROM activities``.  Relative file
paths inside a query (``read_parquet('data/samples/*.parquet')``) resolve from the
repo root regardless of the working directory.
"""

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
QUERY_DIR = ROOT / "querys"
DB_PATH = ROOT / "data" / "activities.db"


def connect(db: Path | str = DB_PATH, *, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with ``db`` attached as the ``data`` catalog."""
    con = duckdb.connect()
    con.execute(f"SET file_search_path = '{ROOT}'")
    con.execute(f"ATTACH '{db}' AS data{' (READ_ONLY)' if read_only else ''}")
    con.execute("USE data")
    return con


def run_query(
    name: str, *, db: Path | str = DB_PATH, read_only: bool = False, **params
) -> pd.DataFrame:
    """Execute ``querys/<name>.sql`` and return the last result as a DataFrame.

    Keyword arguments are bound as query parameters, e.g. ``run_query("activity",
    activity_id=123)`` fills ``$activity_id`` in the SQL.
    """
    sql = (QUERY_DIR / f"{name}.sql").read_text()
    with connect(db, read_only=read_only) as con:
        return con.execute(sql, params).df()


if __name__ == "__main__":
    import sys

    print(run_query(sys.argv[1]))
