"""Model training for the Services/ML layer.

Strict model separation:
  XGBoost          -> fraud classification          (binary)
  XGBoost          -> scam category classification  (multiclass)
  XGBoost          -> repayment-risk prediction     (binary)
  Isolation Forest -> transaction/behavioural anomaly detection ONLY

The model interfaces are deliberately thin (feature matrix in, probability
out) so LightGBM (or anything else) can be substituted later by swapping the
trainer + the registry entry — no service code changes required.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from app.services import datagen, feature_store
from app.services.feature_store import (
    FEATURE_NAMES_BORROWER,
    FEATURE_NAMES_TX,
)

logger = logging.getLogger("riskguard.training")


def _utc_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

FRAUD_FILE = "fraud_xgboost.joblib"
SCAM_FILE = "scam_xgboost.joblib"
REPAYMENT_FILE = "repayment_xgboost.joblib"
ANOMALY_FILE = "anomaly_isolation_forest.joblib"
META_FILE = "model_meta.json"


# ---------------------------------------------------------------------------
# dataset builders (deterministic)
# ---------------------------------------------------------------------------
def build_fraud_dataset(seed: int) -> tuple[list[dict], np.ndarray, np.ndarray, np.ndarray]:
    pool = datagen.generate_transaction_pool(seed)
    txs = pool["transactions"]
    y = np.asarray([1 if t["label_is_fraud"] else 0 for t in txs], dtype=np.int32)
    X = feature_store.build_transaction_matrix(txs, y.tolist())
    scam = np.asarray([t["label_scam_category"] or "" for t in txs], dtype=object)
    return txs, X, y, scam


def build_repayment_dataset(seed: int) -> tuple[np.ndarray, np.ndarray]:
    """Offline training universe — same generator as the demo data, so
    training and serving see one distribution."""
    rng = np.random.default_rng(seed + 7)
    accounts = datagen.build_accounts()
    borrowers, loans, repayments = datagen.generate_borrower_universe(rng, 2400, accounts)

    reps_by_loan: dict[str, list[dict]] = {}
    for r in repayments:
        reps_by_loan.setdefault(r["loan_id"], []).append(r)
    loans_by_borrower: dict[str, list[dict]] = {}
    for ln in loans:
        loans_by_borrower.setdefault(ln["borrower_id"], []).append(ln)

    X_rows, y_rows = [], []
    noise = rng.normal(0, 1, size=len(borrowers))
    for i, b in enumerate(borrowers):
        b_loans = loans_by_borrower.get(b["id"], [])
        b_reps = [r for ln in b_loans for r in reps_by_loan.get(ln["id"], [])]
        X_rows.append(
            feature_store.build_repayment_features(b, b_loans, b_reps, now=datagen.DATA_END)
        )
        # Ground truth label: serious delinquency observed/imminent in 90 days.
        # Derived from the latent stress + exogenous noise, i.e. partially
        # predictable from the observable early-warning features.
        latent = b["stress"] + 0.22 * noise[i]
        y_rows.append(1 if latent > 0.58 else 0)
    return np.asarray(X_rows, dtype=np.float32), np.asarray(y_rows, dtype=np.int32)


# ---------------------------------------------------------------------------
# trainers
# ---------------------------------------------------------------------------
def _binary_metrics(model, X_te, y_te) -> dict:
    proba = model.predict_proba(X_te)[:, 1]
    pred = (proba >= 0.5).astype(int)
    return {
        "roc_auc": round(float(roc_auc_score(y_te, proba)), 4),
        "accuracy": round(float(accuracy_score(y_te, pred)), 4),
        "precision": round(float(precision_score(y_te, pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_te, pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_te, pred, zero_division=0)), 4),
        "test_rows": int(len(y_te)),
        "positive_rate": round(float(np.mean(y_te)), 4),
    }


def _fit_xgb(X, y, seed: int, multiclass: bool = False) -> XGBClassifier:
    params = dict(
        n_estimators=350,
        max_depth=5,
        learning_rate=0.08,
        subsample=0.9,
        colsample_bytree=0.9,
        min_child_weight=3,
        reg_lambda=1.2,
        eval_metric="logloss" if not multiclass else "mlogloss",
        random_state=seed,
        n_jobs=-1,
        verbosity=0,
    )
    if multiclass:
        params.update(objective="multi:softprob")
    model = XGBClassifier(**params)
    model.fit(X, y)
    return model


def train_fraud_model(seed: int) -> tuple[dict, dict]:
    txs, X, y, _ = build_fraud_dataset(seed)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y
    )
    model = _fit_xgb(X_tr, y_tr, seed)
    metrics = _binary_metrics(model, X_te, y_te)
    artifact = {
        "kind": "xgboost_fraud",
        "backend": "xgboost",
        "task": "binary_fraud_classification",
        "model": model,
        "feature_names": FEATURE_NAMES_TX,
        "metrics": metrics,
        "trained_at": _utc_iso(),
        "seed": seed,
    }
    logger.info("fraud model trained: %s", metrics)
    return artifact, metrics


def train_scam_model(seed: int) -> tuple[dict, dict]:
    txs, X, y, _ = build_fraud_dataset(seed)
    mask = y == 1
    X = X[mask]
    labels_raw = np.asarray([t["label_scam_category"] or "unknown" for t in txs])[mask]
    classes = sorted(set(labels_raw.tolist()))
    label_to_idx = {c: i for i, c in enumerate(classes)}
    y_idx = np.asarray([label_to_idx[c] for c in labels_raw], dtype=np.int32)

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y_idx, test_size=0.25, random_state=seed, stratify=y_idx
    )
    model = _fit_xgb(X_tr, y_tr, seed, multiclass=True)
    pred = model.predict(X_te)
    metrics = {
        "accuracy": round(float(accuracy_score(y_te, pred)), 4),
        "f1_macro": round(float(f1_score(y_te, pred, average="macro", zero_division=0)), 4),
        "classes": classes,
        "test_rows": int(len(y_te)),
    }
    artifact = {
        "kind": "xgboost_scam",
        "backend": "xgboost",
        "task": "multiclass_scam_category",
        "model": model,
        "feature_names": FEATURE_NAMES_TX,
        "classes": classes,
        "metrics": metrics,
        "trained_at": _utc_iso(),
        "seed": seed,
    }
    logger.info("scam model trained: %s", metrics)
    return artifact, metrics


def train_repayment_model(seed: int) -> tuple[dict, dict]:
    X, y = build_repayment_dataset(seed)
    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=seed, stratify=y
    )
    model = _fit_xgb(X_tr, y_tr, seed)
    metrics = _binary_metrics(model, X_te, y_te)
    artifact = {
        "kind": "xgboost_repayment",
        "backend": "xgboost",
        "task": "binary_repayment_risk",
        "model": model,
        "feature_names": FEATURE_NAMES_BORROWER,
        "metrics": metrics,
        "trained_at": _utc_iso(),
        "seed": seed,
    }
    logger.info("repayment model trained: %s", metrics)
    return artifact, metrics


def train_anomaly_model(seed: int) -> tuple[dict, dict]:
    txs, X, y, _ = build_fraud_dataset(seed)
    X_normal = X[y == 0]  # Isolation Forest learns "normal behaviour" only
    iso = IsolationForest(
        n_estimators=200,
        contamination=0.04,
        max_samples="auto",
        random_state=seed,
        n_jobs=-1,
    )
    iso.fit(X_normal)
    raw = iso.decision_function(X_normal)           # higher = more normal
    score_max = float(np.percentile(raw, 99))       # normal anchor
    score_min = float(np.percentile(raw, 1))        # anomalous anchor
    artifact = {
        "kind": "isolation_forest",
        "backend": "sklearn",
        "task": "transaction_behavioural_anomaly_detection",
        "model": iso,
        "feature_names": FEATURE_NAMES_TX,
        "normal_anchor": score_max,
        "anomaly_anchor": score_min,
        "metrics": {
            "train_rows": int(len(X_normal)),
            "contamination": 0.04,
            "note": "Isolation Forest is used ONLY for anomaly detection, never for fraud classification.",
        },
        "trained_at": _utc_iso(),
        "seed": seed,
    }
    logger.info("isolation forest trained on %s normal rows", len(X_normal))
    return artifact, metrics_anomaly(artifact, X_normal)


def metrics_anomaly(artifact: dict, X_normal: np.ndarray) -> dict:
    iso = artifact["model"]
    raw = iso.decision_function(X_normal)
    return {
        "train_rows": int(len(X_normal)),
        "contamination": 0.04,
        "mean_normal_anomaly_score": round(
            float(np.mean(_iso_score(raw, artifact))), 3
        ),
        "note": "Isolation Forest is used ONLY for anomaly detection, never for fraud classification.",
    }


def _iso_score(raw: np.ndarray, artifact: dict) -> np.ndarray:
    hi = artifact["normal_anchor"]
    lo = artifact["anomaly_anchor"]
    span = (hi - lo) or 1.0
    return np.clip((hi - raw) / span * 100.0, 0, 100)



# ---------------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------------
def train_all(model_dir: Path, seed: int = 42, force: bool = False) -> dict:
    """Train + persist every model. Idempotent unless `force=True`."""
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, dict] = {}
    jobs = {
        "fraud": (FRAUD_FILE, lambda: train_fraud_model(seed)),
        "scam": (SCAM_FILE, lambda: train_scam_model(seed)),
        "repayment": (REPAYMENT_FILE, lambda: train_repayment_model(seed)),
        "anomaly": (ANOMALY_FILE, lambda: train_anomaly_model(seed)),
    }
    for kind, (filename, fn) in jobs.items():
        path = model_dir / filename
        if path.exists() and not force:
            try:
                art = joblib.load(path)
                summary[kind] = {"skipped": True, "metrics": art.get("metrics", {})}
                continue
            except Exception:  # corrupt artifact -> retrain
                logger.exception("could not reload %s, retraining", path)
        artifact, metrics = fn()
        joblib.dump(artifact, path)
        summary[kind] = {"skipped": False, "metrics": metrics, "path": str(path)}
        logger.info("saved %s -> %s", kind, path)

    meta = {
        "generated_at": _utc_iso(),
        "seed": seed,
        "models": {k: v.get("metrics", {}) for k, v in summary.items()},
    }
    (model_dir / META_FILE).write_text(json.dumps(meta, indent=2))
    return summary


if __name__ == "__main__":  # pragma: no cover
    import sys

    from app.config import get_settings

    logging.basicConfig(level=logging.INFO)
    s = get_settings()
    result = train_all(s.model_dir, s.demo_seed, force="--force" in sys.argv)
    print(json.dumps(result, indent=2, default=str))
