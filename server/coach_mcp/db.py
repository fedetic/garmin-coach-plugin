"""sqlite access for the athlete database. Writes go through `insert`/`upsert`,
which validate table and column names against the live schema; free-form SQL
is read-only."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "data" / "schema.sql"
SCHEMA_VERSION = 1

ENUMS = {
    ("observations", "type"): {"fact", "calculation", "interpretation", "hypothesis", "decision"},
    ("observations", "confidence"): {"HIGH", "MEDIUM", "LOW"},
    ("milestones", "confidence"): {"HIGH", "MEDIUM", "LOW"},
    ("agent_reviews", "verdict"): {"APPROVE", "CONDITIONAL", "REJECT"},
    ("checkins", "kind"): {"daily", "weekly", "block_review", "test"},
    ("checkins", "risk"): {"GREEN", "YELLOW", "ORANGE", "RED"},
    ("injuries", "status"): {"active", "monitoring", "resolved"},
}


def path(root: Path) -> Path:
    return root / "data" / "coach.db"


def connect(root: Path) -> sqlite3.Connection:
    p = path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    fresh = not p.exists()
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    if fresh:
        con.executescript(SCHEMA.read_text())
        con.execute("INSERT INTO schema_version VALUES (?)", (SCHEMA_VERSION,))
        con.commit()
    return con


def columns(con: sqlite3.Connection, table: str) -> list[str]:
    cols = [r["name"] for r in con.execute(f"PRAGMA table_info({table})")]
    if not cols:
        raise ValueError(f"unknown table: {table}")
    return cols


def _validate(con, table: str, record: dict) -> dict:
    cols = set(columns(con, table))
    unknown = set(record) - cols
    if unknown:
        raise ValueError(f"{table} has no column(s) {sorted(unknown)}; columns are {sorted(cols)}")
    for (t, c), allowed in ENUMS.items():
        if t == table and record.get(c) is not None and record[c] not in allowed:
            raise ValueError(f"{table}.{c} must be one of {sorted(allowed)}, got {record[c]!r}")
    return record


def insert(con, table: str, records: list[dict]) -> list[int]:
    ids = []
    for rec in records:
        rec = _validate(con, table, rec)
        keys = list(rec)
        cur = con.execute(
            f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            [rec[k] for k in keys],
        )
        ids.append(cur.lastrowid)
    con.commit()
    return ids


def upsert(con, table: str, records: list[dict], conflict: list[str]) -> int:
    n = 0
    for rec in records:
        rec = _validate(con, table, rec)
        keys = list(rec)
        updates = [k for k in keys if k not in conflict]
        sql = (f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))}) "
               f"ON CONFLICT({', '.join(conflict)}) DO ")
        sql += f"UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in updates)}" if updates else "NOTHING"
        con.execute(sql, [rec[k] for k in keys])
        n += 1
    con.commit()
    return n


def update(con, table: str, row_id, fields: dict, key: str = "id") -> int:
    fields = _validate(con, table, fields)
    if key not in columns(con, table):
        raise ValueError(f"{table} has no column {key}")
    cur = con.execute(
        f"UPDATE {table} SET {', '.join(f'{k}=?' for k in fields)} WHERE {key}=?",
        [*fields.values(), row_id],
    )
    con.commit()
    return cur.rowcount


_READONLY = re.compile(r"^\s*(select|with|pragma\s+table_info)\b", re.I)


def query(root: Path, sql: str, params: list | None = None, limit: int = 200) -> list[dict]:
    if not _READONLY.match(sql) or ";" in sql.strip().rstrip(";"):
        raise ValueError("query() is read-only: a single SELECT/WITH statement")
    connect(root).close()  # make sure the db exists with the schema
    con = sqlite3.connect(f"file:{path(root)}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(sql, params or []).fetchmany(limit)
        return [dict(r) for r in rows]
    finally:
        con.close()
