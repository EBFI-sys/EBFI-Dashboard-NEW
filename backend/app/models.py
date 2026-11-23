"""Database schema for EBFI Ops.

Money columns are Numeric; computed P&L values are never stored except the
rate snapshot written into a job line when its month is closed.
"""
import datetime as dt
from decimal import Decimal

from sqlalchemy import (JSON, Boolean, Column, Date, DateTime, ForeignKey, Integer, Numeric, String,
                        Table, Text, UniqueConstraint, func)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

Money = Numeric(14, 2)
Rate = Numeric(12, 4)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SoftDelete:
    deleted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", index=True)


# ---------------------------------------------------------------- people
class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    initials: Mapped[str] = mapped_column(String(8), unique=True)  # «Чья»: LR, SV, MB, LM
    role: Mapped[str] = mapped_column(String(20))  # admin | accountant | manager | archived
    password_hash: Mapped[str | None] = mapped_column(String(200))
    totp_secret: Mapped[str | None] = mapped_column(String(64))
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    legacy_letters: Mapped[str | None] = mapped_column(String(20))
    color: Mapped[str | None] = mapped_column(String(9))  # «Чья» label colour, #rrggbb  # old Cyrillic letters, e.g. "Л"
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40))  # morning digest goes here
    digest: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


# ---------------------------------------------------------------- references
class Country(Base):
    __tablename__ = "countries"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    region: Mapped[str] = mapped_column(String(40), default="Other")


class Vendor(Base):
    """Factories / vendors where inspections take place; offered as suggestions when typing."""
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(300), unique=True)
    country: Mapped[str | None] = mapped_column(String(80))
    notes: Mapped[str | None] = mapped_column(Text)


class FinalClient(Base):
    """End customers behind our clients (ADNOC, Seatrium…): the «Финальный клиент» of a request."""
    __tablename__ = "final_clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    notes: Mapped[str | None] = mapped_column(Text)


class PaymentMethod(Base):
    __tablename__ = "payment_methods"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    rko_percent: Mapped[Decimal] = mapped_column(Rate, default=0)  # % of the contractor cost
    rko_fixed_inr: Mapped[Decimal] = mapped_column(Money, default=0)  # fixed fee per payment, INR


class Client(Base, TimestampMixin, SoftDelete):
    __tablename__ = "clients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)  # each legal entity is its own client
    legal_name: Mapped[str | None] = mapped_column(String(200))
    is_indian: Mapped[bool] = mapped_column(Boolean, default=False)  # GST and TDS apply only if True
    gstin: Mapped[str | None] = mapped_column(String(20))
    state: Mapped[str | None] = mapped_column(String(60))  # Indian state, for CGST+SGST vs IGST
    invoice_template: Mapped[str | None] = mapped_column(String(4))  # code of the Word template, app/invoice_rules.py
    default_currency: Mapped[str] = mapped_column(String(3), default="USD")
    job_code: Mapped[str | None] = mapped_column(String(4))
    color: Mapped[str | None] = mapped_column(String(9))  # label colour in the Табель, #rrggbb
    address: Mapped[str | None] = mapped_column(Text)  # billing address printed on invoices
    wht: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # client withholds WHT (5%)
    sp_folder: Mapped[str | None] = mapped_column(String(200))  # name of its folder on the server, e.g. «TUV R QATAR»  # KK in job number YY.KK-NNN; shared by e.g. all BV entities
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)


class Inspector(Base, TimestampMixin, SoftDelete):
    __tablename__ = "inspectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    country: Mapped[str | None] = mapped_column(String(80))
    specialization: Mapped[str | None] = mapped_column(String(200))
    rate: Mapped[Decimal | None] = mapped_column(Money)
    currency: Mapped[str | None] = mapped_column(String(3))
    email: Mapped[str | None] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(60))
    payment_method_id: Mapped[int | None] = mapped_column(ForeignKey("payment_methods.id"))
    bank_details_enc: Mapped[str | None] = mapped_column(Text)  # Fernet-encrypted
    notes: Mapped[str | None] = mapped_column(Text)


class FxRate(Base):
    __tablename__ = "fx_rates"
    __table_args__ = (UniqueConstraint("month", "currency"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    currency: Mapped[str] = mapped_column(String(3))  # USD | EUR | GBP
    rate: Mapped[Decimal] = mapped_column(Rate)  # INR per 1 unit, RBI rate on the last day of the month


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))


class MonthClose(Base):
    __tablename__ = "month_closes"
    month: Mapped[str] = mapped_column(String(7), primary_key=True)
    closed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


# ---------------------------------------------------------------- work
class Request(Base, TimestampMixin, SoftDelete):
    __tablename__ = "requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    received_date: Mapped[dt.date | None] = mapped_column(Date)
    type: Mapped[str] = mapped_column(String(30), default="Inspection")  # Inspection | Audit | Expediting
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"))
    final_client: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(80))
    factory: Mapped[str | None] = mapped_column(String(300))
    dates_text: Mapped[str | None] = mapped_column(String(200))
    client_rate: Mapped[Decimal | None] = mapped_column(Money)
    client_currency: Mapped[str | None] = mapped_column(String(3))
    inspector_rate: Mapped[Decimal | None] = mapped_column(Money)
    inspector_currency: Mapped[str | None] = mapped_column(String(3))
    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("inspectors.id"))
    inspector_ids: Mapped[list | None] = mapped_column(JSON)  # inspectors whose CVs were sent
    proposed_cvs: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="В процессе")
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id"))
    notes: Mapped[str | None] = mapped_column(Text)


class Job(Base, TimestampMixin, SoftDelete):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_number: Mapped[str] = mapped_column(String(30), unique=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    client_contact: Mapped[str | None] = mapped_column(String(120))
    client_job_number: Mapped[str | None] = mapped_column(String(120))
    vendor: Mapped[str | None] = mapped_column(String(300))
    country: Mapped[str | None] = mapped_column(String(80))
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(20), default="В работе")  # В работе | Пауза | Завершен
    pre_november: Mapped[bool] = mapped_column(Boolean, default=False)  # opened before the system
    sp_folder_id: Mapped[str | None] = mapped_column(String(100))  # OneDrive folder of the job (id survives renames)
    sp_folder_url: Mapped[str | None] = mapped_column(Text)
    sp_error: Mapped[str | None] = mapped_column(Text)  # last failure talking to OneDrive, shown on the job card
    # a closed month of this job was changed later than 24 h after closing: the row is purple until checked
    late_edit_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    late_edit_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    late_edit_months: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    service_type: Mapped[str | None] = mapped_column(String(30))  # Inspection | Audit | Expediting → «Inspection subject»
    equipment: Mapped[str | None] = mapped_column(String(300))
    cargo: Mapped[str | None] = mapped_column(String(120))  # marine surveys: type of cargo
    tonnage: Mapped[Decimal | None] = mapped_column(Numeric(14, 3))  # marine surveys: MT
    lines: Mapped[list["JobLine"]] = relationship(back_populates="job", order_by="JobLine.month")
    client: Mapped[Client] = relationship()


class JobLine(Base, TimestampMixin, SoftDelete):
    __tablename__ = "job_lines"
    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)
    grp: Mapped[int] = mapped_column(Integer, default=1, server_default="1")  # lines of one inspector on the job, split by month
    inspector_id: Mapped[int | None] = mapped_column(ForeignKey("inspectors.id"))
    dates_text: Mapped[str | None] = mapped_column(String(300))
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    unit: Mapped[str] = mapped_column(String(10), default="day")  # day | hour | ton | lump
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    client_rate: Mapped[Decimal] = mapped_column(Money, default=0)
    inspector_rate: Mapped[Decimal] = mapped_column(Money, default=0)
    inspector_currency: Mapped[str | None] = mapped_column(String(3))  # None = same as the client currency
    overtime_client: Mapped[Decimal] = mapped_column(Money, default=0)
    overtime_inspector: Mapped[Decimal] = mapped_column(Money, default=0)
    no_subcontractor: Mapped[bool] = mapped_column(Boolean, default=False)
    payment_method_id: Mapped[int | None] = mapped_column(ForeignKey("payment_methods.id"))
    rko_override_inr: Mapped[Decimal | None] = mapped_column(Money)
    sales_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("sales_invoices.id"))
    # snapshot written when the month is closed; afterwards these are used instead of live settings
    snap_fx: Mapped[Decimal | None] = mapped_column(Rate)
    snap_fx_insp: Mapped[Decimal | None] = mapped_column(Rate)
    snap_gst: Mapped[Decimal | None] = mapped_column(Rate)
    snap_wht: Mapped[Decimal | None] = mapped_column(Rate)  # WHT rate applied when the month was closed (0 = none)
    snap_tds: Mapped[Decimal | None] = mapped_column(Rate)
    snap_admin: Mapped[Decimal | None] = mapped_column(Rate)
    snap_indian: Mapped[bool | None] = mapped_column(Boolean)
    snap_rko_inr: Mapped[Decimal | None] = mapped_column(Money)
    notes: Mapped[str | None] = mapped_column(Text)
    job: Mapped[Job] = relationship(back_populates="lines")


class SalesInvoice(Base, TimestampMixin, SoftDelete):
    __tablename__ = "sales_invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)  # EBFI-2627-NNN
    date: Mapped[dt.date | None] = mapped_column(Date)
    client_id: Mapped[int] = mapped_column(ForeignKey("clients.id"))
    currency: Mapped[str] = mapped_column(String(3))
    amount: Mapped[Decimal] = mapped_column(Money)  # without GST, in invoice currency
    status: Mapped[str] = mapped_column(String(30), default="Not Verified")  # Not Verified | Отправлен клиенту | Paid
    sp_file_id: Mapped[str | None] = mapped_column(String(100))  # the invoice PDF in Outgoing Invoice Register
    sp_file_url: Mapped[str | None] = mapped_column(Text)
    received_amount: Mapped[Decimal | None] = mapped_column(Money)
    payment_date: Mapped[dt.date | None] = mapped_column(Date)
    fx_rate: Mapped[Decimal | None] = mapped_column(Rate)
    taxable_inr: Mapped[Decimal | None] = mapped_column(Money)
    cgst: Mapped[Decimal] = mapped_column(Money, default=0)
    sgst: Mapped[Decimal] = mapped_column(Money, default=0)
    igst: Mapped[Decimal] = mapped_column(Money, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    extra_lines: Mapped[list | None] = mapped_column(JSON)  # rows added in the invoice dialog (lab analysis, draft survey…)
    doc_url: Mapped[str | None] = mapped_column(Text)  # Word file on OneDrive
    pdf_url: Mapped[str | None] = mapped_column(Text)
    annex_url: Mapped[str | None] = mapped_column(Text)


class CreditNote(Base, TimestampMixin, SoftDelete):
    """CN-2627-NNN against a client invoice: the same document with «CREDIT NOTE PASS AGAINST INVOICE № …»."""
    __tablename__ = "credit_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(40), unique=True)
    date: Mapped[dt.date | None] = mapped_column(Date)
    sales_invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoices.id"))
    client_id: Mapped[int | None] = mapped_column(ForeignKey("clients.id"))
    currency: Mapped[str | None] = mapped_column(String(3))
    amount: Mapped[Decimal | None] = mapped_column(Money)
    gst_inr: Mapped[Decimal | None] = mapped_column(Money)
    line_ids: Mapped[list | None] = mapped_column(JSON)  # the invoice lines at the time of the credit note
    released: Mapped[bool] = mapped_column(Boolean, default=False)  # its jobs were freed to be invoiced again
    reason: Mapped[str | None] = mapped_column(Text)
    doc_url: Mapped[str | None] = mapped_column(Text)
    pdf_url: Mapped[str | None] = mapped_column(Text)


class TdsEntry(Base, TimestampMixin):
    __tablename__ = "tds_register"
    id: Mapped[int] = mapped_column(primary_key=True)
    sales_invoice_id: Mapped[int] = mapped_column(ForeignKey("sales_invoices.id"), unique=True)
    amount_inr: Mapped[Decimal] = mapped_column(Money)
    quarter: Mapped[str] = mapped_column(String(10))  # FY27-Q3
    status: Mapped[str] = mapped_column(String(30), default="Ожидается")  # Ожидается | В Form 26AS | Зачтён
    notes: Mapped[str | None] = mapped_column(Text)


inspector_invoice_jobs = Table(
    "inspector_invoice_jobs", Base.metadata,
    Column("inspector_invoice_id", ForeignKey("inspector_invoices.id"), primary_key=True),
    Column("job_id", ForeignKey("jobs.id"), primary_key=True),
)


class InspectorInvoice(Base, TimestampMixin, SoftDelete):
    __tablename__ = "inspector_invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str | None] = mapped_column(String(60))
    inspector_id: Mapped[int] = mapped_column(ForeignKey("inspectors.id"))
    invoice_date: Mapped[dt.date | None] = mapped_column(Date)
    dates_text: Mapped[str | None] = mapped_column(String(300))
    days: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    rate: Mapped[Decimal | None] = mapped_column(Money)
    amount: Mapped[Decimal] = mapped_column(Money)
    currency: Mapped[str] = mapped_column(String(3))
    payment_method_id: Mapped[int | None] = mapped_column(ForeignKey("payment_methods.id"))
    paid: Mapped[bool] = mapped_column(Boolean, default=False)
    paid_date: Mapped[dt.date | None] = mapped_column(Date)
    file_path: Mapped[str | None] = mapped_column(String(300))
    sp_file_id: Mapped[str | None] = mapped_column(String(100))  # the invoice PDF in Incoming Invoice Register
    sp_file_url: Mapped[str | None] = mapped_column(Text)
    comment: Mapped[str | None] = mapped_column(Text)
    jobs: Mapped[list[Job]] = relationship(secondary=inspector_invoice_jobs)


# ---------------------------------------------------------------- audit
class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    table_name: Mapped[str] = mapped_column(String(40), index=True)
    record_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(10))  # insert | update | delete
    changes: Mapped[dict] = mapped_column(JSON)
