"""Model registry: artifact loading, health status and the fallback contract.

Fallback contract (spec):
  1. the API must never crash because a model is missing/broken
  2. the failure is logged
  3. a deterministic rule-based scorer is used instead
  4. the response explicitly reports model_used="fallback",
     prediction_status="fallback"
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.services import risk_config as rc

logger = logging.getLogger("riskguard.models")

ARTIFACT_FILES = {
    "fraud": "fraud_xgboost.joblib",
    "scam": "scam_xgboost.joblib",
    "repayment": "repayment_xgboost.joblib",
    "anomaly": "anomaly_isolation_forest.joblib",
}

_cache: dict[str, Any | None] = {}
_errors: dict[str, str] = {}
_lock = threading.Lock()


def reset() -> None:
    """Drop cached artifacts (call after retraining)."""
    with _lock:
        _cache.clear()
        _errors.clear()


def model_path(kind: str) -> Path:
    return Path(get_settings().model_dir) / ARTIFACT_FILES[kind]


def get_artifact(kind: str) -> dict | None:
    """Load (and cache) an artifact. Returns None when unavailable — callers
    MUST fall back rather than raise."""
    with _lock:
        if kind in _cache:
            return _cache[kind]
        path = model_path(kind)
        if not path.exists():
            _cache[kind] = None
            _errors[kind] = f"artifact not found: {path}"
            logger.error("[model-fallback] %s unavailable: %s", kind, _errors[kind])
            return None
        try:
            import joblib

            artifact = joblib.load(path)
            _cache[kind] = artifact
            _errors.pop(kind, None)
            logger.info("loaded model artifact '%s' from %s", kind, path)
            return artifact
        except Exception as exc:  # never propagate — API must not crash
            _cache[kind] = None
            _errors[kind] = f"{type(exc).__name__}: {exc}"
            logger.exception("[model-fallback] failed to load model '%s'", kind)
            return None


def force_fallback() -> bool:
    return bool(get_settings().force_fallback)


def status() -> dict[str, dict]:
    """Model health for GET /api/health and the dashboard model-health card."""
    out: dict[str, dict] = {}
    for kind in ARTIFACT_FILES:
        art = get_artifact(kind)
        out[kind] = {
            "loaded": art is not None,
            "model_used": (art or {}).get("backend", rc.MODEL_FALLBACK),
            "kind": (art or {}).get("kind"),
            "task": (art or {}).get("task"),
            "trained_at": (art or {}).get("trained_at"),
            "metrics": (art or {}).get("metrics", {}),
            "error": _errors.get(kind),
            "forced_fallback": force_fallback(),
        }
    return out
