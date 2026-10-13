"""Idempotent demo bootstrap.

    schema -> synthetic data -> model training -> analysis pass -> alerts/interventions

Run:  python -m app.seed [--rebuild] [--force-train] [--force-analysis]
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys

from sqlalchemy import func, select

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.models import Account, Alert, Borrower, Intervention, Loan, Repayment, Transaction
from app.services import (
    datagen,
    early_warning_service,
    fraud_service,
    intervention_service,
    model_registry,
    repayment_service,
    training,
)
from app.services import risk_config as rc

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("riskguard.seed")

CHUNK = 500


def _insert_chunks(db, rows: list) -> None:
    for i in range(0, len(rows), CHUNK):
        db.add_all(rows[i : i + CHUNK])
        db.flush()
    db.commit()


def generate_data(db, seed: int) -> dict:
    data = datagen.generate_transaction_pool(seed)

    _insert_chunks(db, [Account(**a) for a in data["accounts"]])

    borrower_rows = []
    for b in data["borrowers"]:
        payload = {k: v for k, v in b.items() if k not in {"stress", "scenario"}}
        borrower_rows.append(Borrower(**payload))
    _insert_chunks(db, borrower_rows)

    loan_rows = []
    for ln in data["loans"]:
        payload = {k: v for k, v in ln.items() if k != "stress"}
        loan_rows.append(Loan(**payload))
    _insert_chunks(db, loan_rows)

    _insert_chunks(db, [Repayment(**r) for r in data["repayments"]])

    tx_rows = []
    for i, t in enumerate(data["transactions"], start=1):
        payload = dict(t)
        payload["id"] = f"TXN-{i:06d}"
        payload["ts"] = payload["ts"].replace(tzinfo=None)
        tx_rows.append(Transaction(**payload))
    _insert_chunks(db, tx_rows)

    counts = {
        "accounts": len(data["accounts"]),
        "borrowers": len(data["borrowers"]),
        "loans": len(data["loans"]),
        "repayments": len(data["repayments"]),
        "transactions": len(tx_rows),
        "fraud_transactions": sum(1 for t in data["transactions"] if t["label_is_fraud"]),
    }
    logger.info("inserted demo data: %s", counts)
    return counts


# ---------------------------------------------------------------------------
# analysis pass (real model inference over the seeded dataset)
# ---------------------------------------------------------------------------
def run_analysis(db) -> dict:
    fraud_service.invalidate_cache()
    repayment_service.invalidate_cache()

    logger.info("fraud analysis pass (XGBoost + Isolation Forest + SHAP)...")
    results = fraud_service.score_all(db)
    rows = list(
        db.scalars(select(Transaction).order_by(Transaction.ts, Transaction.id)).all()
    )
    assert len(rows) == len(results), f"row/result mismatch {len(rows)} != {len(results)}"

    mappings = []
    for row, res in zip(rows, results):
        scam = res["scam"]
        mappings.append(
            {
                "id": row.id,
                "fraud_score": float(res["score"]),
                "fraud_risk_category": res["risk_category"],
                "fraud_model_used": res["model_used"],
                "fraud_prediction_status": res["prediction_status"],
                "fraud_confidence": res["confidence"],
                "fraud_decision": res["decision"],
                "fraud_explanation": res["explanation"],
                "anomaly_score": res["anomaly"]["anomaly_score"],
                "is_anomaly": res["anomaly"]["is_anomaly"],
                "anomaly_explanation": res["anomaly"]["explanation"],
                "scam_category": scam["scam_category"],
                "scam_confidence": scam["confidence"],
                "scam_model_used": scam["model_used"],
                "scam_explanation": scam["explanation"],
            }
        )
    for i in range(0, len(mappings), CHUNK):
        db.bulk_update_mappings(Transaction, mappings[i : i + CHUNK])
    db.commit()
    db.expire_all()  # bulk updates bypass the identity map — refresh cached rows

    logger.info("repayment analysis pass...")
    repayment_results = repayment_service.score_all(db)
    borrower_rows = list(db.scalars(select(Borrower)).all())
    b_mappings = []
    for b in borrower_rows:
        res = repayment_results.get(b.id)
        if res is None:
            continue
        b_mappings.append(
            {
                "id": b.id,
                "repayment_score": float(res["score"]),
                "repayment_category": res["risk_category"],
                "repayment_model_used": res["model_used"],
                "repayment_prediction_status": res["prediction_status"],
                "repayment_confidence": res["confidence"],
            }
        )
    if b_mappings:
        db.bulk_update_mappings(Borrower, b_mappings)
        db.commit()
        db.expire_all()

    fraud_service.invalidate_cache()
    repayment_service.invalidate_cache()
    return {
        "transactions_scored": len(mappings),
        "borrowers_scored": len(b_mappings),
        "fraud_model_used": mappings[0]["fraud_model_used"] if mappings else None,
        "repayment_model_used": b_mappings[0]["repayment_model_used"] if b_mappings else None,
    }


# ---------------------------------------------------------------------------
# alerts + interventions
# ---------------------------------------------------------------------------
def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


def create_alerts(db) -> int:
    if db.scalar(select(func.count(Alert.id))) or 0:
        return 0
    created = 0
    now = _utcnow()

    suspicious = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.fraud_score >= rc.FRAUD_SUSPICIOUS_THRESHOLD)
            .order_by(Transaction.fraud_score.desc())
            .limit(120)
        ).all()
    )
    for tx in suspicious:
        severity = "critical" if tx.fraud_score >= 81 else "high"
        reasons = []
        if tx.scam_category and tx.scam_category not in {"none", "unknown"}:
            reasons.append(f"Predicted scam category: {rc.SCAM_LABELS.get(tx.scam_category, tx.scam_category)}")
        if tx.is_anomaly:
            reasons.append("Isolation Forest anomaly detected on the same transaction")
        reasons.append(f"Fraud risk score {int(tx.fraud_score)}/100 ({tx.fraud_risk_category})")
        db.add(
            Alert(
                kind="fraud",
                severity=severity,
                subject_type="transaction",
                subject_id=tx.id,
                title=f"Suspicious transaction {tx.id} · ₹{tx.amount:,.0f}",
                message=tx.fraud_explanation or "High fraud-risk score.",
                reasons=reasons,
                score=tx.fraud_score,
                status="open",
                created_at=now,
            )
        )
        created += 1

    anomalies = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.is_anomaly.is_(True), Transaction.fraud_score < rc.FRAUD_SUSPICIOUS_THRESHOLD)
            .order_by(Transaction.anomaly_score.desc())
            .limit(60)
        ).all()
    )
    for tx in anomalies:
        db.add(
            Alert(
                kind="anomaly",
                severity="medium",
                subject_type="transaction",
                subject_id=tx.id,
                title=f"Behavioural anomaly on {tx.id} · ₹{tx.amount:,.0f}",
                message=tx.anomaly_explanation or "Unusual behaviour detected.",
                reasons=["Anomaly ≠ fraud: flagged for observation only"],
                score=tx.anomaly_score,
                status="open",
                created_at=now,
            )
        )
        created += 1

    for b in db.scalars(select(Borrower)).all():
        ctx = repayment_service.load_context(db, b.id)
        if ctx is None:
            continue
        signals = early_warning_service.evaluate(
            ctx["borrower"], ctx["loans"], ctx["repayments"]
        )
        level = early_warning_service.warning_level(signals)
        if level in {"none", "low"}:
            continue
        db.add(
            Alert(
                kind="early_warning",
                severity="high" if level in {"high", "critical"} else "medium",
                subject_type="borrower",
                subject_id=b.id,
                title=f"Early financial stress — {b.name}",
                message=early_warning_service.summary(signals),
                reasons=[f"[{s['severity']}] {s['label']}: {s['message']}" for s in signals],
                score=b.repayment_score,
                status="open",
                created_at=now,
            )
        )
        created += 1

    db.commit()
    logger.info("created %s alerts", created)
    return created


def create_interventions(db) -> int:
    if db.scalar(select(func.count(Intervention.id))) or 0:
        return 0
    created = 0

    suspicious = list(
        db.scalars(
            select(Transaction)
            .where(Transaction.fraud_score >= rc.FRAUD_SUSPICIOUS_THRESHOLD)
            .order_by(Transaction.fraud_score.desc())
            .limit(30)
        ).all()
    )
    for i, tx in enumerate(suspicious):
        analysis = {
            "score": tx.fraud_score,
            "anomaly": {"is_anomaly": tx.is_anomaly},
        }
        recs = intervention_service.recommend_for_fraud(analysis)
        for rec in recs[:2]:
            row = intervention_service.create(
                db,
                {
                    "category": "fraud",
                    "action": rec["action"],
                    "title": f"{rec['action']} — {tx.id}",
                    "description": rec["description"],
                    "priority": rec["priority"],
                    "subject_type": "transaction",
                    "subject_id": tx.id,
                },
                auto=True,
            )
            created += 1
            final_status = ["Completed", "In Progress", "Pending"][i % 3]
            if final_status != "Pending":
                payload: dict = {"status": final_status, "note": "Analyst actioned the recommendation."}
                if final_status == "Completed":
                    payload["outcome"] = (
                        f"Transaction {tx.id} reviewed: score {int(tx.fraud_score)}/100, "
                        f"decision '{tx.fraud_decision}'. Customer contacted and flow monitored."
                    )
                intervention_service.update(db, row, payload)

    stressed = list(
        db.scalars(
            select(Borrower)
            .where(Borrower.repayment_score >= rc.FRAUD_SUSPICIOUS_THRESHOLD)
            .order_by(Borrower.repayment_score.desc())
            .limit(10)
        ).all()
    )
    for i, b in enumerate(stressed):
        recs = intervention_service.recommend_for_loan(
            {"score": b.repayment_score, "prediction_status": b.repayment_prediction_status},
            warning_level="high",
        )
        for rec in recs[:2]:
            row = intervention_service.create(
                db,
                {
                    "category": "loan",
                    "action": rec["action"],
                    "title": f"{rec['action']} — {b.name}",
                    "description": rec["description"],
                    "priority": rec["priority"],
                    "subject_type": "borrower",
                    "subject_id": b.id,
                },
                auto=True,
            )
            created += 1
            final_status = ["In Progress", "Pending", "Completed"][i % 3]
            if final_status != "Pending":
                payload = {"status": final_status, "note": "Assigned to the credit-risk desk."}
                if final_status == "Completed":
                    payload["outcome"] = (
                        f"Reached borrower; repayment plan reviewed against score "
                        f"{int(b.repayment_score)}/100 ({b.repayment_category})."
                    )
                intervention_service.update(db, row, payload)

    logger.info("created %s interventions", created)
    return created


# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed RiskGuard demo data + models")
    parser.add_argument("--rebuild", action="store_true", help="DROP and recreate all tables")
    parser.add_argument("--force-train", action="store_true", help="retrain models even if present")
    parser.add_argument("--force-analysis", action="store_true", help="rerun the analysis pass")
    args = parser.parse_args(argv)

    settings = get_settings()

    if args.rebuild:
        logger.warning("--rebuild: dropping all tables")
        Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        tx_count = db.scalar(select(func.count(Transaction.id))) or 0
        if tx_count == 0:
            if settings.seed_demo_data:
                generate_data(db, settings.demo_seed)
            else:
                logger.warning("SEED_DEMO_DATA=false and database is empty")
        else:
            logger.info("database already holds %s transactions — skipping generation", tx_count)

        logger.info("training models (idempotent)...")
        training.train_all(settings.model_dir, settings.demo_seed, force=args.force_train)
        model_registry.reset()

        needs_analysis = args.force_analysis or tx_count == 0 or (
            db.scalar(
                select(func.count(Transaction.id)).where(Transaction.fraud_score.is_(None))
            )
            or 0
        ) > 0
        if needs_analysis:
            stats = run_analysis(db)
            logger.info("analysis complete: %s", stats)
        else:
            logger.info("analysis already present — skipping")

        alerts = create_alerts(db)
        interventions = create_interventions(db)
        logger.info("alerts created: %s | interventions created: %s", alerts, interventions)

        fraud_status = model_registry.status()
        logger.info(
            "model health: fraud=%s repayment=%s anomaly=%s scam=%s",
            fraud_status["fraud"]["loaded"],
            fraud_status["repayment"]["loaded"],
            fraud_status["anomaly"]["loaded"],
            fraud_status["scam"]["loaded"],
        )
        print(
            "\n=== RiskGuard seed complete ===\n"
            f"transactions: {db.scalar(select(func.count(Transaction.id)))}\n"
            f"borrowers:    {db.scalar(select(func.count(Borrower.id)))}\n"
            f"alerts:       {db.scalar(select(func.count(Alert.id)))}\n"
            f"interventions:{db.scalar(select(func.count(Intervention.id)))}\n"
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
