"""FastAPI application — the API boundary between React and the services/ML layer.

Route handlers stay thin: validate -> call a service -> return JSON.
No ML logic lives here.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    alerts,
    borrowers,
    dashboard,
    fraud,
    graph,
    health,
    interventions,
    loans,
    transactions,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger("riskguard.api")

settings = get_settings()

app = FastAPI(
    title="FINTECHSICO — Financial Risk & Fraud Intelligence API",
    version=settings.app_version,
    description=(
        "React → FastAPI → Services/ML Layer → PostgreSQL. "
        "XGBoost handles fraud classification and repayment-risk prediction, "
        "Isolation Forest handles anomaly detection, SHAP explains predictions, "
        "and NetworkX analyses money flow."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    health.router,
    dashboard.router,
    transactions.router,
    fraud.router,
    borrowers.router,
    loans.router,
    graph.router,
    alerts.router,
    interventions.router,
):
    app.include_router(router, prefix=settings.api_prefix)


@app.get("/")
def root() -> dict:
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "api": settings.api_prefix,
        "architecture": "React -> FastAPI -> Services/ML Layer -> PostgreSQL",
    }


@app.on_event("startup")
def log_model_health() -> None:  # pragma: no cover
    from app.services import model_registry

    status = model_registry.status()
    for kind, info in status.items():
        if info["loaded"]:
            logger.info("model %-10s loaded (%s)", kind, info["kind"])
        else:
            logger.warning(
                "[model-fallback] model %-10s NOT loaded: %s — requests will use the "
                "deterministic fallback and report prediction_status='fallback'",
                kind,
                info["error"],
            )
