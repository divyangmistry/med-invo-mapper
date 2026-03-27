"""
test_database.py — Standalone test for all database operations.

Run from the project root (no Docker needed, uses an in-memory SQLite DB):
    python tests/test_database.py

What it tests
-------------
  ✓ Database initialisation (table creation)
  ✓ Vendor creation (new + duplicate)
  ✓ Medicine creation (new + duplicate)
  ✓ Vendor↔Medicine mapping upsert (first insert + repeat update)
  ✓ Transaction logging
  ✓ Transaction count verification
"""
import os
import sys

# Point to in-memory DB for tests — no file system side effects
os.environ["DATABASE_URL"] = "sqlite://"       # In-memory SQLite
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"  # Not used by DB tests
os.environ["VLM_MODEL"] = "qwen2-vl:7b"

# Ensure agent/ is on the path regardless of where the test is run from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "agent"))

from database import (
    init_db, get_session,
    get_or_create_vendor, get_or_create_medicine,
    upsert_mapping, log_transaction,
    Vendor, Medicine, VendorMapping, Transaction,
)

PASS = "✅"
FAIL = "❌"
results = []


def check(name: str, condition: bool, detail: str = "") -> None:
    icon = PASS if condition else FAIL
    msg = f"  {icon}  {name}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append(condition)


print("\n" + "=" * 55)
print("  Med-Invo Mapper — Database Unit Tests")
print("=" * 55)

# ── Test 1: init_db ──────────────────────────────────────────
print("\n[1/6] Database initialisation")
try:
    init_db()
    check("Tables created without error", True)
except Exception as e:
    check("Tables created without error", False, str(e))

# ── Test 2: Vendor creation ──────────────────────────────────
print("\n[2/6] Vendor creation")
session = get_session()
try:
    v1 = get_or_create_vendor(session, "Cipla Ltd.")
    check("New vendor created", v1.id is not None, f"id={v1.id}")
    v2 = get_or_create_vendor(session, "Cipla Ltd.")   # Should reuse
    check("Duplicate vendor returns same record", v1.id == v2.id, f"same id={v1.id}")
    v3 = get_or_create_vendor(session, "Sun Pharma")
    check("Second vendor created with different id", v3.id != v1.id)
    session.commit()
finally:
    session.close()

# ── Test 3: Medicine creation ─────────────────────────────────
print("\n[3/6] Medicine creation")
session = get_session()
try:
    m1 = get_or_create_medicine(session, "Azithromycin 500mg", "AZM500")
    check("New medicine created", m1.id is not None, f"id={m1.id}")
    m2 = get_or_create_medicine(session, "Azithromycin 500mg", "AZM500")  # Reuse
    check("Duplicate medicine returns same record", m1.id == m2.id)
    m3 = get_or_create_medicine(session, "Paracetamol 650mg", "PCM650")
    check("Second medicine created", m3.id != m1.id)
    session.commit()
finally:
    session.close()

# ── Test 4: Vendor↔Medicine mapping ──────────────────────────
print("\n[4/6] Vendor↔Medicine mapping (agent memory)")
session = get_session()
try:
    v = get_or_create_vendor(session, "Cipla Ltd.")
    m = get_or_create_medicine(session, "Azithromycin 500mg", "AZM500")
    mapping1 = upsert_mapping(session, v, m)
    check("Mapping created", mapping1 is not None)
    session.commit()

    # Second call should update occurrence_count
    mapping2 = upsert_mapping(session, v, m)
    session.commit()
    check("Repeated mapping increments count",
          (mapping2.occurrence_count or 0) >= 2,
          f"count={mapping2.occurrence_count}")
finally:
    session.close()

# ── Test 5: Transaction logging ───────────────────────────────
print("\n[5/6] Transaction logging")
try:
    payload = {
        "vendor_name": "Cipla Ltd.",
        "invoice_number": "INV-2024-001",
        "medicine_name": "Azithromycin 500mg",
        "medicine_code": "AZM500",
        "batch_number": "B20240301",
        "manufacturing_date": "03/2024",
        "expiry_date": "03/2026",
        "quantity": 10,
    }
    txn = log_transaction(payload, confidence_flag="OK", source_image="test_invoice.jpg")
    check("Transaction logged", txn.id is not None, f"txn_id={txn.id}")
    check("Confidence flag saved correctly", txn.confidence_flag == "OK")
    check("Source image saved", txn.source_image == "test_invoice.jpg")
except Exception as e:
    check("Transaction logged", False, str(e))

# ── Test 6: Count verification ────────────────────────────────
print("\n[6/6] Record count verification")
session = get_session()
try:
    vendor_count = session.query(Vendor).count()
    medicine_count = session.query(Medicine).count()
    mapping_count = session.query(VendorMapping).count()
    txn_count = session.query(Transaction).count()
    check(f"Vendors in DB", vendor_count >= 2, f"count={vendor_count}")
    check(f"Medicines in DB", medicine_count >= 2, f"count={medicine_count}")
    check(f"Mappings in DB", mapping_count >= 1, f"count={mapping_count}")
    check(f"Transactions in DB", txn_count >= 1, f"count={txn_count}")
finally:
    session.close()

# ── Summary ───────────────────────────────────────────────────
passed = sum(results)
total = len(results)
print("\n" + "=" * 55)
if passed == total:
    print(f"  ✅  ALL {total} DATABASE TESTS PASSED")
else:
    print(f"  ❌  {total - passed} / {total} TESTS FAILED")
print("=" * 55 + "\n")
sys.exit(0 if passed == total else 1)
