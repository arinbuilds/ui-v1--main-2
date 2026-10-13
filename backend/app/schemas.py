"""Pydantic request/response schemas — the API contract between React and FastAPI."""
from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Channel = Literal["upi", "wallet", "card", "netbanking"]


# --------------------------------------------------------------------------
# Shared risk-score payload (shape required by the product spec)
# --------------------------------------------------------------------------
class Factor(BaseModel):
    feature: str
    label: str
    value: str
    contribution: float
    direction: str  # increase | decrease


class RiskScore(BaseModel):
    score: float
    risk_category: str
    model_used: str
    prediction_status: str
    confidence: Optional[float] = None
    confidence_method: Optional[str] = None
    explanation: str
    factors: list[Factor] = Field(default_factory=list)


class AnomalyResult(BaseModel):
    anomaly_score: float
    is_anomaly: bool
    model_used: str
    prediction_status: str
    drivers: list[str] = Field(default_factory=list)
    explanation: str


class ScamClassification(BaseModel):
    scam_category: str
    confidence: float
    model_used: str
    prediction_status: str
    explanation: str


class FraudAnalysis(RiskScore):
    transaction_id: str
    decision: str
    decision_note: str
    anomaly: AnomalyResult
    scam: ScamClassification


class RepaymentAnalysis(RiskScore):
    borrower_id: str
    borrower_name: str
    loan_ids: list[str] = Field(default_factory=list)


class ShapContribution(BaseModel):
    feature: str
    label: str
    value: str
    contribution: float
    direction: str


class ShapExplanation(BaseModel):
    borrower_id: str
    score: float
    risk_category: str
    model_used: str
    prediction_status: str
    base_value: float
    contributions: list[ShapContribution] = Field(default_factory=list)
    increasing: list[ShapContribution] = Field(default_factory=list)
    decreasing: list[ShapContribution] = Field(default_factory=list)
    summary: str
    chart: list[dict] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------
class FraudPredictRequest(BaseModel):
    """Normalized transaction payload accepted by POST /api/fraud/predict."""

    model_config = ConfigDict(extra="ignore")

    sender_account_id: str = Field(min_length=1, max_length=24)
    receiver_account_id: str = Field(min_length=1, max_length=24)
    amount: float = Field(gt=0, le=100_000_000)
    channel: Channel
    merchant_category: str = "general"
    purpose: str = "transfer"
    relationship: str = "unknown"
    city: str = "unknown"
    device_id: str = "unknown"
    narrative: str = ""
    ts: Optional[dt.datetime] = None
    counterparty_is_new: Optional[bool] = None


class InterventionCreate(BaseModel):
    category: Literal["fraud", "loan"]
    action: str
    title: str
    description: str = ""
    priority: Literal["low", "medium", "high", "critical"] = "medium"
    subject_type: str
    subject_id: str


class InterventionUpdate(BaseModel):
    status: Optional[Literal["Pending", "In Progress", "Completed"]] = None
    outcome: Optional[str] = None
    note: Optional[str] = None


class AlertUpdate(BaseModel):
    status: Optional[Literal["open", "acknowledged", "resolved"]] = None


class HealthResponse(BaseModel):
    status: str
    app: str
    version: str
    environment: str
    database: str
    models: dict
