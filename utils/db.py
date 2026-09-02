"""Query the DuckDB store and the Parquet files under ``data/`` with DuckDB.

* ``run_query("build_activities")`` runs ``querys/build_activities.sql``.
* ``sql("SELECT ...")`` runs an ad-hoc query string.

Both return the final statement's result as a DataFrame.  The store at
``data/activities.db`` is attached as the catalog ``data`` (so a query can say
``FROM activities`` or ``FROM data.activities``), and relative file paths inside a
query (``read_parquet('data/details_raw/*.parquet')``) resolve from the repo root
regardless of the working directory.  Pass ``attach=False`` to skip the store
entirely when you only need the Parquet files.
"""

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
QUERY_DIR = ROOT / "querys"
DB_PATH = ROOT / "data" / "activities.db"


def connect(
    db: Path | str = DB_PATH, *, attach: bool = True, read_only: bool = False
) -> duckdb.DuckDBPyConnection:
    """In-memory DuckDB connection with file paths rooted at the repo.

    With ``attach`` (default) the store at ``db`` is attached as the catalog
    ``data`` and made current.  With ``attach=False`` no database is opened —
    useful for querying only the Parquet files, and it never touches the store's
    lock.
    """
    con = duckdb.connect()
    con.execute(f"SET file_search_path = '{ROOT}'")
    if attach:
        if not Path(db).exists():
            # ATTACH would otherwise silently create an empty file and every
            # query would fail with a confusing "table does not exist".
            raise FileNotFoundError(
                f"No DuckDB store at {db}. Build it from the notebook first "
                "(normalize activities -> CREATE TABLE activities_raw)."
            )
        con.execute(f"ATTACH '{db}' AS data{' (READ_ONLY)' if read_only else ''}")
        con.execute("USE data")
    return con


def run_query(
    name: str, *, db: Path | str = DB_PATH, attach: bool = True, read_only: bool = False, **params
) -> pd.DataFrame:
    """Execute ``querys/<name>.sql`` and return the last result as a DataFrame.

    Keyword arguments are bound as query parameters, e.g. ``run_query("activity",
    activity_id=123)`` fills ``$activity_id`` in the SQL.
    """
    text = (QUERY_DIR / f"{name}.sql").read_text()
    with connect(db, attach=attach, read_only=read_only) as con:
        return con.execute(text, params).df()


def sql(
    query: str,
    params: object = None,
    *,
    db: Path | str = DB_PATH,
    attach: bool = True,
    read_only: bool = False,
) -> pd.DataFrame:
    """Run an ad-hoc query string and return the last result as a DataFrame.

    ``attach`` (default) also exposes the ``activities`` view, so a query over the
    Parquet detail files can join it::

        sql('''
            SELECT s.* FROM read_parquet('data/details_raw/*.parquet', union_by_name := true) s
            JOIN activities a USING (activity_id)
            WHERE a.sport = 'running'
        ''')
    """
    with connect(db, attach=attach, read_only=read_only) as con:
        return con.execute(query, params or []).df()


if __name__ == "__main__":
    import sys

    print(run_query(sys.argv[1]))
