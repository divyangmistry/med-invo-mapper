"""
database.py — SQLAlchemy ORM models and helper functions.

Tables
------
  vendors           : unique vendor index
  medicines         : unique medicine / drug index
  vendor_mappings   : agent "memory" – which medicine was seen with which vendor
  transactions      : full audit log of every extraction event
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, create_engine, event
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from config import Config

logger = logging.getLogger(__name__)


# ── ORM Base ─────────────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── Models ───────────────────────────────────────────────────────────────────

class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_name = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    mappings = relationship("VendorMapping", back_populates="vendor")
    transactions = relationship("Transaction", back_populates="vendor")

    def __repr__(self) -> str:
        return f"<Vendor id={self.id} name={self.vendor_name!r}>"


class Medicine(Base):
    __tablename__ = "medicines"

    id = Column(Integer, primary_key=True, autoincrement=True)
    medicine_name = Column(String(255), nullable=False)
    medicine_code = Column(String(100), nullable=False, unique=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    mappings = relationship("VendorMapping", back_populates="medicine")
    transactions = relationship("Transaction", back_populates="medicine")

    def __repr__(self) -> str:
        return f"<Medicine id={self.id} code={self.medicine_code!r} name={self.medicine_name!r}>"


class VendorMapping(Base):
    """Agent memory — tracks which medicines have been seen from which vendor."""
    __tablename__ = "vendor_mappings"
    __table_args__ = (UniqueConstraint("vendor_id", "medicine_id", name="uq_vendor_medicine"),)

    vendor_id = Column(Integer, ForeignKey("vendors.id"), primary_key=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), primary_key=True)
    first_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime, default=lambda: datetime.now(timezone.utc),
                       onupdate=lambda: datetime.now(timezone.utc))
    occurrence_count = Column(Integer, default=1)

    vendor = relationship("Vendor", back_populates="mappings")
    medicine = relationship("Medicine", back_populates="mappings")


class Invoice(Base):
    """Invoice-level header and totals — one record per invoice image."""
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    bill_date = Column(String(20), nullable=True)
    entry_date = Column(String(20), nullable=True)
    entry_number = Column(String(50), nullable=True)
    tax_type = Column(String(100), nullable=True)
    payment_type = Column(String(50), nullable=True)
    pan_number = Column(String(20), nullable=True)
    # ── Totals ──
    total_base = Column(String(20), nullable=True)
    sgst_amount = Column(String(20), nullable=True)
    cgst_amount = Column(String(20), nullable=True)
    igst_amount = Column(String(20), nullable=True)
    cess_amount = Column(String(20), nullable=True)
    discount_total = Column(String(20), nullable=True)
    total_amount = Column(String(20), nullable=True)
    other_charges = Column(String(20), nullable=True)
    credit_note = Column(String(20), nullable=True)
    tcs_value = Column(String(20), nullable=True)
    source_image = Column(String(500), nullable=True)
    raw_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    vendor = relationship("Vendor")
    transactions = relationship("Transaction", back_populates="invoice")

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} number={self.invoice_number!r}>"


class Transaction(Base):
    """Full audit log of every extraction event (one row per line item)."""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    invoice_number = Column(String(100), nullable=True)
    batch_number = Column(String(100), nullable=True)
    manufacturing_date = Column(String(20), nullable=True)
    expiry_date = Column(String(20), nullable=True)
    quantity = Column(Integer, default=1)
    # ── New financial columns ──
    unit = Column(String(50), nullable=True)
    free_quantity = Column(Integer, default=0)
    mrp = Column(String(20), nullable=True)
    ptr = Column(String(20), nullable=True)
    discount_percent = Column(String(10), nullable=True)
    discount_amount = Column(String(20), nullable=True)
    base_amount = Column(String(20), nullable=True)
    gst_percent = Column(String(10), nullable=True)
    amount = Column(String(20), nullable=True)
    hsn_code = Column(String(50), nullable=True)
    location = Column(String(100), nullable=True)
    # ── Audit ──
    raw_json = Column(Text, nullable=True)
    confidence_flag = Column(String(20), default="OK")
    source_image = Column(String(500), nullable=True)

    vendor = relationship("Vendor", back_populates="transactions")
    medicine = relationship("Medicine", back_populates="transactions")
    invoice = relationship("Invoice", back_populates="transactions")

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} vendor={self.vendor_id} medicine={self.medicine_id}>"


# ── Engine & Session Factory ──────────────────────────────────────────────────

_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            Config.DATABASE_URL,
            connect_args={"check_same_thread": False, "timeout": 30},
            echo=False,
        )
        # Enable WAL mode for SQLite (better concurrent reads)
        if "sqlite" in Config.DATABASE_URL:
            @event.listens_for(_engine, "connect")
            def set_wal(dbapi_conn, _):
                dbapi_conn.execute("PRAGMA journal_mode=WAL")
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    return _SessionLocal()


def init_db() -> None:
    """Create all tables if they don't already exist."""
    Base.metadata.create_all(bind=get_engine())
    logger.info("Database initialised — tables ready.")


# ── Helper Functions ──────────────────────────────────────────────────────────

def get_or_create_vendor(session: Session, vendor_name: str) -> Vendor:
    """Return an existing Vendor or create a new one."""
    name = vendor_name.strip()
    vendor = session.query(Vendor).filter(
        Vendor.vendor_name.ilike(name)
    ).first()
    if vendor is None:
        vendor = Vendor(vendor_name=name)
        session.add(vendor)
        session.flush()
        logger.info("New vendor created: %r", name)
    return vendor


def get_or_create_medicine(session: Session, medicine_name: str, medicine_code: str) -> Medicine:
    """Return an existing Medicine matched by BOTH code and name.

    Two medicines can arrive from the LLM with the same generic code (e.g.
    code='1' or code='4567') but different names.  Matching on code alone
    would silently return the wrong medicine record and later cause a
    duplicate (vendor_id, medicine_id) in vendor_mappings, rolling back the
    entire session.  We therefore use (code, name) as the effective key.
    """
    code = medicine_code.strip().upper()
    name = medicine_name.strip()
    # Try exact (code + name) match first
    medicine = session.query(Medicine).filter_by(
        medicine_code=code, medicine_name=name
    ).first()
    if medicine is None:
        # If the code is truly unique and unambiguous, reuse it
        existing_by_code = session.query(Medicine).filter_by(medicine_code=code).all()
        if len(existing_by_code) == 0:
            medicine = Medicine(medicine_name=name, medicine_code=code)
            session.add(medicine)
            session.flush()
            logger.info("New medicine created: code=%r name=%r", code, name)
        else:
            # Code clash — different name for an already-used code.
            # Mint a disambiguated code so the UNIQUE constraint is not violated.
            disambig_code = f"{code}__{name[:30].replace(' ', '_').upper()}"
            medicine = session.query(Medicine).filter_by(medicine_code=disambig_code).first()
            if medicine is None:
                medicine = Medicine(medicine_name=name, medicine_code=disambig_code)
                session.add(medicine)
                session.flush()
                logger.warning(
                    "Medicine code clash: original code=%r already used by a different name. "
                    "Created disambiguated code=%r for name=%r",
                    code, disambig_code, name,
                )
    return medicine


def upsert_mapping(session: Session, vendor: Vendor, medicine: Medicine) -> VendorMapping:
    """Insert or update the vendor↔medicine mapping (agent memory)."""
    mapping = session.query(VendorMapping).filter_by(
        vendor_id=vendor.id, medicine_id=medicine.id
    ).first()
    if mapping is None:
        mapping = VendorMapping(vendor_id=vendor.id, medicine_id=medicine.id)
        session.add(mapping)
        logger.info("New vendor-medicine mapping: %r ↔ %r", vendor.vendor_name, medicine.medicine_code)
    else:
        mapping.last_seen = datetime.now(timezone.utc)
        mapping.occurrence_count = (mapping.occurrence_count or 0) + 1
        logger.debug("Updated mapping: %r ↔ %r (count=%d)",
                     vendor.vendor_name, medicine.medicine_code, mapping.occurrence_count)
    return mapping


def log_transaction(
    extraction: dict,
    confidence_flag: str = "OK",
    source_image: Optional[str] = None,
) -> list[Transaction]:
    """
    Persist multiple extraction items to the database.

    Creates an Invoice record for header/totals, then one Transaction per
    line item.  Each item is wrapped in its own savepoint so that a
    constraint error on one item only rolls back *that item*.

    Parameters
    ----------
    extraction : dict  — parsed VLM result (all invoice fields + items)
    confidence_flag    — 'OK', 'RETRY', or 'MANUAL_REVIEW'
    source_image       — filename of the processed image

    Returns
    -------
    list[Transaction] — list of the successfully committed transaction records
    """
    import json

    session = get_session()
    transactions = []
    try:
        vendor_name = extraction.get("vendor_name", "UNKNOWN")
        invoice_number = extraction.get("invoice_number", "UNKNOWN")
        items = extraction.get("items", [])

        if not items:
            logger.warning("No items to log for invoice %s", invoice_number)
            return []

        vendor = get_or_create_vendor(session, vendor_name)
        raw_json_str = json.dumps(extraction, ensure_ascii=False)

        # ── Create Invoice record (header + totals) ───────────────────────
        invoice = Invoice(
            vendor_id=vendor.id,
            invoice_number=invoice_number,
            bill_date=extraction.get("bill_date"),
            entry_date=extraction.get("entry_date"),
            entry_number=extraction.get("entry_number"),
            tax_type=extraction.get("tax_type"),
            payment_type=extraction.get("payment_type"),
            pan_number=extraction.get("pan_number"),
            total_base=extraction.get("total_base"),
            sgst_amount=extraction.get("sgst_amount"),
            cgst_amount=extraction.get("cgst_amount"),
            igst_amount=extraction.get("igst_amount"),
            cess_amount=extraction.get("cess_amount"),
            discount_total=extraction.get("discount_total"),
            total_amount=extraction.get("total_amount"),
            other_charges=extraction.get("other_charges"),
            credit_note=extraction.get("credit_note"),
            tcs_value=extraction.get("tcs_value"),
            source_image=source_image,
            raw_json=raw_json_str,
        )
        session.add(invoice)
        session.flush()  # get invoice.id

        for idx, item in enumerate(items):
            sp = session.begin_nested()
            try:
                med_name = item.get("medicine_name", "UNKNOWN")
                med_code = item.get("medicine_code", "UNKNOWN")

                medicine = get_or_create_medicine(session, med_name, med_code)
                upsert_mapping(session, vendor, medicine)

                txn = Transaction(
                    vendor_id=vendor.id,
                    medicine_id=medicine.id,
                    invoice_id=invoice.id,
                    invoice_number=invoice_number,
                    batch_number=item.get("batch_number"),
                    manufacturing_date=item.get("manufacturing_date"),
                    expiry_date=item.get("expiry_date"),
                    quantity=int(item.get("quantity", 1)),
                    unit=item.get("unit"),
                    free_quantity=int(item.get("free_quantity", 0)),
                    mrp=item.get("mrp"),
                    ptr=item.get("ptr"),
                    discount_percent=item.get("discount_percent"),
                    discount_amount=item.get("discount_amount"),
                    base_amount=item.get("base_amount"),
                    gst_percent=item.get("gst_percent"),
                    amount=item.get("amount"),
                    hsn_code=item.get("hsn_code"),
                    location=item.get("location"),
                    raw_json=raw_json_str,
                    confidence_flag=confidence_flag,
                    source_image=source_image,
                )
                session.add(txn)
                sp.commit()
                transactions.append(txn)
                logger.debug("Item %d/%d saved: %r", idx + 1, len(items), med_name)
            except Exception as item_exc:
                sp.rollback()
                logger.error(
                    "Failed to save item %d/%d (%r / %r): %s — skipping this item.",
                    idx + 1, len(items), item.get("medicine_name"), item.get("medicine_code"), item_exc,
                )

        session.commit()
        for txn in transactions:
            session.refresh(txn)

        logger.info(
            "Logged %d/%d transactions for invoice %r vendor %r (invoice_id=%d)",
            len(transactions), len(items), invoice_number, vendor_name, invoice.id,
        )
        return transactions
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
