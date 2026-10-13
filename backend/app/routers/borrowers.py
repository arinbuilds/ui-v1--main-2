"""Borrower endpoints — profiles, repayment risk, SHAP, timeline, warnings."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Borrower, Loan, Repayment, Transaction
from app.schemas import RepaymentAnalysis, ShapExplanation
from app.services import early_warning_service, repayment_service, risk_config as rc

router = APIRouter(prefix="/borrowers", tags=["borrowers"])


@router.get("")
def list_borrowers(
    db: Session = Depends(get_db),
    q: Optional[str] = None,
    sort: str = Query("score", pattern="^(score|name|income)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    stmt = select(Borrower)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(Borrower.name.ilike(like), Borrower.id.ilike(like), Borrower.city.ilike(like))
        )
    total = db.scalar(select(func.count(Borrower.id))) if not q else None
    rows = list(db.scalars(stmt).all())

    loan_agg: dict[str, dict] = {}
    for lid, cnt, out in db.execute(
        select(Loan.borrower_id, func.count(Loan.id), func.coalesce(func.sum(Loan.outstanding_amount), 0.0))
        .group_by(Loan.borrower_id)
    ).all():
        loan_agg[lid] = {"loans": cnt, "outstanding": float(out)}

    if sort == "name":
        rows.sort(key=lambda b: b.name)
    elif sort == "income":
        rows.sort(key=lambda b: b.monthly_income, reverse=True)
    else:
        rows.sort(key=lambda b: (b.repayment_score if b.repayment_score is not None else -1), reverse=True)

    items = [
        {
            "id": b.id,
            "name": b.name,
            "city": b.city,
            "employer": b.employer,
            "occupation": b.occupation,
            "account_id": b.account_id,
            "monthly_income": b.monthly_income,
            "monthly_spending": b.monthly_spending,
            "employment_years": b.employment_years,
            "employment_stable": b.employment_stable,
            "credit_utilization": b.credit_utilization,
            "total_existing_debt": b.total_existing_debt,
            "repayment_score": b.repayment_score,
            "repayment_category": b.repayment_category,
            "model_used": b.repayment_model_used,
            "prediction_status": b.repayment_prediction_status,
            "confidence": b.repayment_confidence,
            "loans": loan_agg.get(b.id, {}).get("loans", 0),
            "outstanding": loan_agg.get(b.id, {}).get("outstanding", 0.0),
        }
        for b in rows[offset : offset + limit]
    ]
    return {"total": total if total is not None else len(rows), "items": items}


@router.get("/{borrower_id}")
def borrower_detail(borrower_id: str, db: Session = Depends(get_db)) -> dict:
    ctx = repayment_service.load_context(db, borrower_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="borrower not found")
    b = ctx["borrower"]
    account = db.get(Account, b["account_id"])
    signals = early_warning_service.evaluate(b, ctx["loans"], ctx["repayments"])
    loans = sorted(ctx["loans"], key=lambda l: l["disbursed_at"], reverse=True)
    return {
        **b,
        "account": {
            "id": b["account_id"],
            "name": account.name if account else b["account_id"],
            "bank": account.bank if account else None,
            "city": account.city if account else b["city"],
        },
        "loans": loans,
        "total_outstanding": round(sum(l["outstanding_amount"] for l in loans), 2),
        "total_principal": round(sum(l["principal"] for l in loans), 2),
        "monthly_emi_total": round(
            sum(l["monthly_emi"] for l in loans if l["status"] == "active"), 2
        ),
        "repayment": {
            "score": b["repayment_score"],
            "risk_category": b["repayment_category"],
            "model_used": b["repayment_model_used"],
            "prediction_status": b["repayment_prediction_status"],
            "confidence": b["repayment_confidence"],
        },
        "early_warning": {
            "level": early_warning_service.warning_level(signals),
            "signal_count": len(signals),
            "summary": early_warning_service.summary(signals),
        },
    }


@router.get("/{borrower_id}/repayment-risk", response_model=RepaymentAnalysis)
def repayment_risk(borrower_id: str, db: Session = Depends(get_db)) -> dict:
    """Fresh XGBoost repayment-risk prediction (recomputed in the ML layer)."""
    analysis = repayment_service.score_borrower(db, borrower_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="borrower not found")
    return analysis


@router.get("/{borrower_id}/shap", response_model=ShapExplanation)
def borrower_shap(borrower_id: str, db: Session = Depends(get_db)) -> dict:
    """SHAP explanation for the repayment prediction (computed in the ML layer)."""
    payload = repayment_service.shap_explanation(db, borrower_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="borrower not found")
    return payload


@router.get("/{borrower_id}/early-warnings")
def early_warnings(borrower_id: str, db: Session = Depends(get_db)) -> dict:
    ctx = repayment_service.load_context(db, borrower_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="borrower not found")
    signals = early_warning_service.evaluate(ctx["borrower"], ctx["loans"], ctx["repayments"])
    return {
        "borrower_id": borrower_id,
        "level": early_warning_service.warning_level(signals),
        "signals": signals,
        "summary": early_warning_service.summary(signals),
        "note": "Warnings are leading indicators computed by the services layer; "
        "they do not by themselves mean the loan will default.",
    }


@router.get("/{borrower_id}/timeline")
def borrower_timeline(
    borrower_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(250, ge=1, le=1000),
) -> dict:
    """Combined loan + transaction timeline (disbursement -> spending -> repayment)."""
    ctx = repayment_service.load_context(db, borrower_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail="borrower not found")
    account_id = ctx["borrower"]["account_id"]
    names = {a.id: a.name for a in db.scalars(select(Account)).all()}

    events: list[dict] = []
    for loan in ctx["loans"]:
        events.append(
            {
                "type": "disbursement",
                "ts": loan["disbursed_at"].isoformat(),
                "title": f"Loan disbursed — {loan['purpose']}",
                "amount": loan["principal"],
                "loan_id": loan["id"],
                "status": loan["status"],
                "meta": f"₹{loan['monthly_emi']:,.0f}/mo · {loan['interest_rate']}% · {loan['term_months']} months",
            }
        )
    for r in ctx["repayments"]:
        events.append(
            {
                "type": "repayment",
                "ts": r["due_date"].isoformat(),
                "title": f"EMI due — {r['status'].title()}",
                "amount": r["amount"],
                "paid_amount": r["paid_amount"],
                "status": r["status"],
                "loan_id": r["loan_id"],
                "paid_date": r["paid_date"].isoformat() if r["paid_date"] else None,
                "meta": f"paid {r['paid_amount']:,.0f} of {r['amount']:,.0f}"
                if r["paid_amount"] not in (0.0, r["amount"])
                else "",
            }
        )

    txs = db.scalars(
        select(Transaction)
        .where(
            or_(
                Transaction.sender_account_id == account_id,
                Transaction.receiver_account_id == account_id,
            )
        )
        .order_by(Transaction.ts.desc())
        .limit(limit)
    ).all()
    for t in txs:
        outgoing = t.sender_account_id == account_id
        events.append(
            {
                "type": "transaction",
                "ts": t.ts.isoformat(),
                "title": (
                    f"Outgoing ₹{t.amount:,.0f} → {names.get(t.receiver_account_id, t.receiver_account_id)}"
                    if outgoing
                    else f"Incoming ₹{t.amount:,.0f} ← {names.get(t.sender_account_id, t.sender_account_id)}"
                ),
                "amount": t.amount,
                "direction": "out" if outgoing else "in",
                "tx_id": t.id,
                "loan_id": t.loan_id,
                "spend_category": t.spend_category,
                "channel": t.channel,
                "merchant_category": t.merchant_category,
                "fraud_score": t.fraud_score,
                "risk_category": t.fraud_risk_category,
                "is_anomaly": t.is_anomaly,
                "label": t.label_is_fraud,
            }
        )

    events.sort(key=lambda e: e["ts"], reverse=True)

    # spending breakdown around the loan events (analytical classification only)
    spend: dict[str, dict] = {}
    for t in txs:
        if t.loan_id and t.spend_category:
            bucket = spend.setdefault(t.spend_category, {"category": t.spend_category, "amount": 0.0, "count": 0})
            bucket["amount"] += t.amount
            bucket["count"] += 1
    spend_breakdown = sorted(
        ({**v, "amount": round(v["amount"], 2)} for v in spend.values()),
        key=lambda x: x["amount"],
        reverse=True,
    )

    return {
        "borrower_id": borrower_id,
        "account_id": account_id,
        "events": events[:limit],
        "spend_breakdown": spend_breakdown,
        "spend_note": "Spending categories are an ANALYTICAL classification of transactions "
        "around loan events — a category alone never implies the borrower is risky.",
        "risk_bands": [
            {"from": lo, "to": hi, "label": label, "level": level}
            for lo, hi, label, level in rc.RISK_BANDS
        ],
    }
