"""Dashboard aggregation service — all statistics are computed here (backend),
React only renders them.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Alert, Borrower, Intervention, Transaction
from app.services import intervention_service, model_registry, risk_config as rc


def _week_key(ts: dt.datetime) -> str:
    week_start = ts.date() - dt.timedelta(days=ts.weekday())
    return week_start.isoformat()


def _utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def summary(db: Session) -> dict:
    # ---- transactions ---------------------------------------------------
    tx_rows = db.execute(
        select(
            Transaction.id, Transaction.ts, Transaction.amount, Transaction.channel,
            Transaction.fraud_score, Transaction.is_anomaly, Transaction.scam_category,
            Transaction.fraud_risk_category, Transaction.sender_account_id,
            Transaction.receiver_account_id, Transaction.label_is_fraud,
            Transaction.fraud_prediction_status, Transaction.fraud_model_used,
        )
    ).all()

    total_tx = len(tx_rows)
    total_amount = sum(r[2] for r in tx_rows)
    scores = [r[4] for r in tx_rows if r[4] is not None]
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0
    suspicious = [r for r in tx_rows if (r[4] or 0) >= rc.FRAUD_SUSPICIOUS_THRESHOLD]
    review = [
        r for r in tx_rows
        if rc.FRAUD_REVIEW_THRESHOLD <= (r[4] or 0) < rc.FRAUD_SUSPICIOUS_THRESHOLD
    ]
    anomalies = [r for r in tx_rows if r[5]]
    anomalies_not_fraud = [r for r in anomalies if (r[4] or 0) < rc.FRAUD_SUSPICIOUS_THRESHOLD]

    # weekly trend
    weekly: dict[str, dict] = defaultdict(
        lambda: {"tx_count": 0, "score_sum": 0.0, "score_n": 0, "suspicious": 0, "amount": 0.0, "anomalies": 0}
    )
    histogram = Counter()
    for r in tx_rows:
        wk = _week_key(r[1])
        bucket = weekly[wk]
        bucket["tx_count"] += 1
        bucket["amount"] += r[2]
        if r[4] is not None:
            bucket["score_sum"] += r[4]
            bucket["score_n"] += 1
            if r[4] >= rc.FRAUD_SUSPICIOUS_THRESHOLD:
                bucket["suspicious"] += 1
            lo = int(r[4]) // 10 * 10
            histogram[min(lo, 90)] += 1
        if r[5]:
            bucket["anomalies"] += 1

    trends = [
        {
            "week": wk,
            "tx_count": v["tx_count"],
            "avg_fraud_score": round(v["score_sum"] / v["score_n"], 1) if v["score_n"] else 0,
            "suspicious": v["suspicious"],
            "amount": round(v["amount"], 2),
            "anomalies": v["anomalies"],
        }
        for wk, v in sorted(weekly.items())
    ]

    # scam distribution (predicted scam category over suspicious txs)
    scam_counts = Counter(r[6] for r in suspicious if r[6] and r[6] not in {"none", "unknown"})
    scam_distribution = [
        {
            "key": k,
            "label": rc.SCAM_LABELS.get(k, k),
            "count": v,
        }
        for k, v in scam_counts.most_common()
    ]

    # channel breakdown
    channel_stats: dict[str, dict] = defaultdict(lambda: {"count": 0, "score_sum": 0.0, "score_n": 0, "suspicious": 0})
    for r in tx_rows:
        c = channel_stats[r[3]]
        c["count"] += 1
        if r[4] is not None:
            c["score_sum"] += r[4]
            c["score_n"] += 1
            if r[4] >= rc.FRAUD_SUSPICIOUS_THRESHOLD:
                c["suspicious"] += 1
    channels = [
        {
            "channel": k,
            "count": v["count"],
            "avg_score": round(v["score_sum"] / v["score_n"], 1) if v["score_n"] else 0,
            "suspicious": v["suspicious"],
        }
        for k, v in sorted(channel_stats.items(), key=lambda kv: -kv[1]["count"])
    ]

    score_histogram = [
        {"bucket": f"{lo}-{lo + 9}", "range": lo, "count": histogram.get(lo, 0)}
        for lo in range(0, 100, 10)
    ]

    # ---- borrowers / loans ---------------------------------------------
    borrowers = list(db.scalars(select(Borrower)).all())
    b_scores = [b.repayment_score for b in borrowers if b.repayment_score is not None]
    repayment_categories = Counter(b.repayment_category for b in borrowers if b.repayment_category)
    high_risk_borrowers = sorted(
        [b for b in borrowers if b.repayment_score is not None],
        key=lambda b: b.repayment_score,
        reverse=True,
    )

    # ---- alerts / interventions ----------------------------------------
    alerts = list(db.scalars(select(Alert)).all())
    alert_counts = {
        "total": len(alerts),
        "open": sum(1 for a in alerts if a.status == "open"),
        "acknowledged": sum(1 for a in alerts if a.status == "acknowledged"),
        "resolved": sum(1 for a in alerts if a.status == "resolved"),
        "critical": sum(1 for a in alerts if a.severity == "critical"),
        "high": sum(1 for a in alerts if a.severity == "high"),
        "by_kind": dict(Counter(a.kind for a in alerts)),
    }
    intervention_counts = intervention_service.status_counts(db)

    # ---- model health ----------------------------------------------------
    model_status = model_registry.status()

    # ---- recent suspicious transactions ---------------------------------
    names = {a.id: a.name for a in db.scalars(select(Account)).all()}
    top_suspicious = sorted(suspicious, key=lambda r: (r[4] or 0), reverse=True)[:8]
    recent_alerts = sorted(alerts, key=lambda a: a.created_at or dt.datetime.min, reverse=True)[:8]

    fraud_avg = avg_score
    return {
        "kpis": {
            "transactions_total": total_tx,
            "transaction_volume": round(total_amount, 2),
            "fraud_score_avg": fraud_avg,
            "suspicious_transactions": len(suspicious),
            "review_transactions": len(review),
            "anomalies_detected": len(anomalies),
            "anomalies_not_fraud": len(anomalies_not_fraud),
            "borrowers_total": len(borrowers),
            "repayment_score_avg": round(sum(b_scores) / len(b_scores), 1) if b_scores else 0.0,
            "high_risk_borrowers": sum(1 for b in b_scores if b >= rc.FRAUD_SUSPICIOUS_THRESHOLD),
            "critical_borrowers": sum(1 for s in b_scores if s >= 81),
            "open_alerts": alert_counts["open"],
            "pending_interventions": intervention_counts.get("Pending", 0),
            "fallback_predictions": sum(1 for r in tx_rows if r[11] == rc.PREDICTION_FALLBACK),
        },
        "trends": trends,
        "scam_distribution": scam_distribution,
        "score_histogram": score_histogram,
        "channels": channels,
        "repayment_categories": [
            {"category": k, "label": k, "count": v}
            for k, v in repayment_categories.most_common()
        ],
        "alerts": alert_counts,
        "interventions": intervention_counts,
        "model_status": model_status,
        "risk_bands": [
            {"label": label, "level": level, "from": lo, "to": hi}
            for lo, hi, label, level in rc.RISK_BANDS
        ],
        "top_borrowers": [
            {
                "id": b.id,
                "name": b.name,
                "score": b.repayment_score,
                "category": b.repayment_category,
                "model_used": b.repayment_model_used,
                "prediction_status": b.repayment_prediction_status,
            }
            for b in high_risk_borrowers[:8]
        ],
        "recent_suspicious": [
            {
                "id": r[0],
                "ts": r[1].isoformat(),
                "amount": r[2],
                "channel": r[3],
                "score": r[4],
                "risk_category": r[7],
                "anomaly": bool(r[5]),
                "scam_category": r[6],
                "sender": names.get(r[8], r[8]),
                "receiver": names.get(r[9], r[9]),
            }
            for r in top_suspicious
        ],
        "recent_alerts": [
            {
                "id": a.id,
                "kind": a.kind,
                "severity": a.severity,
                "title": a.title,
                "status": a.status,
                "subject_type": a.subject_type,
                "subject_id": a.subject_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in recent_alerts
        ],
        "generated_at": _utc_iso(),
    }
