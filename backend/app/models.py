"""Modelo de dados. Todos os registros de negócio são isolados por company_id."""
from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="analista")  # admin | analista
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    company: Mapped[Company] = relationship()


class ImportTemplate(Base):
    __tablename__ = "import_templates"
    __table_args__ = (UniqueConstraint("company_id", "source", "signature", name="uq_template_signature"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(20))
    name: Mapped[str] = mapped_column(String(200))
    signature: Mapped[str] = mapped_column(String(40))
    header_row: Mapped[int] = mapped_column(Integer, default=0)
    mapping: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class StagedFile(Base):
    """Registros normalizados de um arquivo validado (o arquivo original NÃO é armazenado)."""
    __tablename__ = "staged_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(300))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    format: Mapped[str] = mapped_column(String(10))
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    records: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Reconciliation(Base):
    __tablename__ = "reconciliations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    code: Mapped[str] = mapped_column(String(40), index=True)
    group_key: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("reconciliations.id"), nullable=True)
    period_start: Mapped[str | None] = mapped_column(String(10), nullable=True)
    period_end: Mapped[str | None] = mapped_column(String(10), nullable=True)
    files: Mapped[list] = mapped_column(JSON, default=list)
    settings_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    totals: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="concluida")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    user: Mapped[User] = relationship()


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(ForeignKey("reconciliations.id", ondelete="CASCADE"), index=True)
    uid: Mapped[str] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(20), index=True)
    row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    settle_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    identifier: Mapped[str] = mapped_column(String(120), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    counterparty: Mapped[str] = mapped_column(String(300), default="")
    amount: Mapped[float] = mapped_column(Numeric(16, 2))
    found_amount: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    difference: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    gross: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    fee: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    kind: Mapped[str | None] = mapped_column(String(30), nullable=True)
    brand: Mapped[str | None] = mapped_column(String(30), nullable=True)
    modality: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    justification: Mapped[str] = mapped_column(Text, default="")
    unmatched_status: Mapped[str] = mapped_column(String(30))
    unmatched_justification: Mapped[str] = mapped_column(Text, default="")
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_ids: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    reconciliation_id: Mapped[int] = mapped_column(ForeignKey("reconciliations.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(20))
    level: Mapped[int] = mapped_column(Integer)
    rule: Mapped[str] = mapped_column(String(60))
    confidence: Mapped[float] = mapped_column(Float)
    state: Mapped[str] = mapped_column(String(20))  # auto | sugerido | aprovado | rejeitado
    status: Mapped[str] = mapped_column(String(30))
    left: Mapped[list] = mapped_column(JSON)
    right: Mapped[list] = mapped_column(JSON)
    left_total: Mapped[float] = mapped_column(Numeric(16, 2))
    right_total: Mapped[float] = mapped_column(Numeric(16, 2))
    difference: Mapped[float] = mapped_column(Numeric(16, 2))
    justification: Mapped[str] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(40), default="")
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class AppSecret(Base):
    """Segredos gerados automaticamente pela aplicação (ex.: chave de assinatura de sessão)."""
    __tablename__ = "app_secrets"
    name: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
