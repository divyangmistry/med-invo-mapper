#!/usr/bin/env python3
"""
migrate_db.py — Lightweight SQLite migration script.

Adds new columns and tables required by the updated schema.
Safe to run multiple times (idempotent).

Usage:
    python agent/migrate_db.py            # uses DATABASE_URL from .env
    python agent/migrate_db.py <db_path>  # explicit path, e.g. ./db/med_invo.db
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def _get_db_path() -> Path:
    """Resolve the SQLite database file path."""
    if len(sys.argv) > 1:
        return Path(sys.argv[1])

    # Try loading from .env / config
    try:
        project_root = Path(__file__).parent.parent.resolve()
        sys.path.insert(0, str(Path(__file__).parent))
        from config import Config
        url = Config.DATABASE_URL
        if url.startswith("sqlite:///"):
            return Path(url.replace("sqlite:///", ""))
    except Exception:
        pass

    # Fallback
    return project_root / "db" / "med_invo.db"


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
    )
    return cur.fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    columns = {row[1] for row in cur.fetchall()}
    return column_name in columns


def _add_column(conn: sqlite3.Connection, table: str, column: str, col_type: str, default=None):
    """Add a column if it doesn't already exist."""
    if _column_exists(conn, table, column):
        return False
    default_clause = f" DEFAULT {default}" if default is not None else ""
    sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}{default_clause}"
    conn.execute(sql)
    print(f"  + {table}.{column} ({col_type})")
    return True


def migrate(db_path: Path):
    """Run all migrations."""
    print(f"Migrating database: {db_path}")

    if not db_path.exists():
        print(f"  Database file not found at {db_path}. It will be created on first run.")
        return

    conn = sqlite3.connect(str(db_path))
    changes = 0

    # ── 1. Create invoices table ─────────────────────────────────────────────
    if not _table_exists(conn, "invoices"):
        print("  Creating 'invoices' table...")
        conn.execute("""
            CREATE TABLE invoices (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vendor_id       INTEGER REFERENCES vendors(id),
                invoice_number  TEXT,
                bill_date       TEXT,
                entry_date      TEXT,
                entry_number    TEXT,
                tax_type        TEXT,
                payment_type    TEXT,
                pan_number      TEXT,
                total_base      TEXT,
                sgst_amount     TEXT,
                cgst_amount     TEXT,
                igst_amount     TEXT,
                cess_amount     TEXT,
                discount_total  TEXT,
                total_amount    TEXT,
                other_charges   TEXT,
                credit_note     TEXT,
                tcs_value       TEXT,
                source_image    TEXT,
                raw_json        TEXT,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        changes += 1
        print("  ✔ 'invoices' table created")

    # ── 2. Add new columns to transactions ───────────────────────────────────
    if _table_exists(conn, "transactions"):
        print("  Checking 'transactions' table for new columns...")
        new_cols = [
            ("invoice_id",       "INTEGER", None),
            ("unit",             "TEXT",    None),
            ("free_quantity",    "INTEGER", "0"),
            ("mrp",              "TEXT",    None),
            ("ptr",              "TEXT",    None),
            ("discount_percent", "TEXT",    None),
            ("discount_amount",  "TEXT",    None),
            ("base_amount",      "TEXT",    None),
            ("gst_percent",      "TEXT",    None),
            ("amount",           "TEXT",    None),
            ("hsn_code",         "TEXT",    None),
            ("location",         "TEXT",    None),
        ]
        for col_name, col_type, default in new_cols:
            if _add_column(conn, "transactions", col_name, col_type, default):
                changes += 1

    conn.commit()
    conn.close()

    if changes:
        print(f"\n✔ Migration complete — {changes} change(s) applied.")
    else:
        print("\n✔ Database is already up to date.")


if __name__ == "__main__":
    db = _get_db_path()
    migrate(db)
