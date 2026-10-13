"""PostgreSQL schema (SQLAlchemy ORM models).

Realistic relational schema: accounts, borrowers, loans, repayments,
transactions (with stored analysis columns), alerts, interventions.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(24))  # individual | business
    bank: Mapped[str] = mapped_column(String(80))
    city: Mapped[str] = mapped_column(String(60))
    role: Mapped[str] = mapped_column(String(32), default="normal")  # normal | mule | scam_infra
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    borrower: Mapped["Borrower | None"] = relationship(back_populates="account")


class Borrower(Base):
    __tablename__ = "borrowers"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(60))
    employer: Mapped[str] = mapped_column(String(120))
    occupation: Mapped[str] = mapped_column(String(80))
    employment_years: Mapped[float] = mapped_column(Float)
    employment_stable: Mapped[bool] = mapped_column(Boolean, default=True)

    monthly_income: Mapped[float] = mapped_column(Float)
    monthly_spending: Mapped[float] = mapped_column(Float)
    total_existing_debt: Mapped[float] = mapped_column(Float, default=0.0)
    credit_limit: Mapped[float] = mapped_column(Float, default=0.0)
    credit_utilization: Mapped[float] = mapped_column(Float, default=0.0)

    income_history: Mapped[list] = mapped_column(JSON, default=list)   # 12 months
    spending_history: Mapped[list] = mapped_column(JSON, default=list)  # 12 months

    # stored (seed-time) repayment analysis ---------------------------------
    repayment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    repayment_category: Mapped[str | None] = mapped_column(String(24), nullable=True)
    repayment_model_used: Mapped[str | None] = mapped_column(String(24), nullable=True)
    repayment_prediction_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    repayment_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    stress_index: Mapped[float] = mapped_column(Float, default=0.0)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    account: Mapped[Account] = relationship(back_populates="borrower")
    loans: Mapped[list["Loan"]] = relationship(back_populates="borrower")


class Loan(Base):
    __tablename__ = "loans"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    borrower_id: Mapped[str] = mapped_column(ForeignKey("borrowers.id"))
    principal: Mapped[float] = mapped_column(Float)
    outstanding_amount: Mapped[float] = mapped_column(Float)
    purpose: Mapped[str] = mapped_column(String(40))       # Business / Education / ...
    intended_use: Mapped[str] = mapped_column(String(40), default="Essential")
    interest_rate: Mapped[float] = mapped_column(Float, default=11.0)
    term_months: Mapped[int] = mapped_column(Integer, default=24)
    monthly_emi: Mapped[float] = mapped_column(Float)
    disbursed_at: Mapped[dt.datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24), default="active")

    borrower: Mapped[Borrower] = relationship(back_populates="loans")
    repayments: Mapped[list["Repayment"]] = relationship(back_populates="loan")


class Repayment(Base):
    __tablename__ = "repayments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    loan_id: Mapped[str] = mapped_column(ForeignKey("loans.id"))
    due_date: Mapped[dt.datetime] = mapped_column(DateTime)
    paid_date: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    amount: Mapped[float] = mapped_column(Float)
    paid_amount: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24))  # paid | late | missed | partial | upcoming

    loan: Mapped[Loan] = relationship(back_populates="repayments")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)
    sender_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    receiver_account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"))
    amount: Mapped[float] = mapped_column(Float)
    channel: Mapped[str] = mapped_column(String(16))         # upi | wallet | card | netbanking
    merchant_category: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(String(32))
    relationship: Mapped[str] = mapped_column(String(24))
    counterparty_is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    city: Mapped[str] = mapped_column(String(60))
    device_id: Mapped[str] = mapped_column(String(32))
    narrative: Mapped[str] = mapped_column(String(200), default="")
    ts: Mapped[dt.datetime] = mapped_column(DateTime)

    loan_id: Mapped[str | None] = mapped_column(ForeignKey("loans.id"), nullable=True)
    spend_category: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # ground-truth labels for the synthetic demo dataset ---------------------
    label_is_fraud: Mapped[bool] = mapped_column(Boolean, default=False)
    label_scam_category: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # stored model analysis (computed by the services layer at seed time) ----
    fraud_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    fraud_risk_category: Mapped[str | None] = mapped_column(String(24), nullable=True)
    fraud_model_used: Mapped[str | None] = mapped_column(String(24), nullable=True)
    fraud_prediction_status: Mapped[str | None] = mapped_column(String(24), nullable=True)
    fraud_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    fraud_decision: Mapped[str | None] = mapped_column(String(24), nullable=True)
    fraud_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    anomaly_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_anomaly: Mapped[bool] = mapped_column(Boolean, default=False)
    anomaly_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    scam_category: Mapped[str | None] = mapped_column(String(32), nullable=True)
    scam_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    scam_model_used: Mapped[str | None] = mapped_column(String(24), nullable=True)
    scam_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_tx_ts", "ts"),
        Index("ix_tx_sender_ts", "sender_account_id", "ts"),
        Index("ix_tx_receiver_ts", "receiver_account_id", "ts"),
        Index("ix_tx_score", "fraud_score"),
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(24))     # fraud | anomaly | early_warning
    severity: Mapped[str] = mapped_column(String(16))  # low | medium | high | critical
    subject_type: Mapped[str] = mapped_column(String(24))  # transaction | borrower | account
    subject_id: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(160))
    message: Mapped[str] = mapped_column(Text)
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="open")  # open | acknowledged | resolved
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_alerts_kind_status", "kind", "status"),)


class Intervention(Base):
    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(16))   # fraud | loan
    action: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(16), default="medium")
    subject_type: Mapped[str] = mapped_column(String(24))
    subject_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="Pending")
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    history: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_interventions_status", "status"),)
