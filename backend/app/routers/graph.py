"""Money-flow graph endpoints (all NetworkX processing happens in the service)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Account, Borrower
from app.services import graph_service

router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/accounts")
def accounts(db: Session = Depends(get_db)) -> dict:
    rows = list(db.scalars(select(Account)).all())
    borrowers = {b.account_id: b for b in db.scalars(select(Borrower)).all()}
    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "entity_type": a.entity_type,
                "bank": a.bank,
                "city": a.city,
                "role": a.role,
                "borrower_id": borrowers[a.id].id if a.id in borrowers else None,
            }
            for a in rows
        ]
    }


@router.get("/money-flow")
def money_flow(
    db: Session = Depends(get_db),
    account_id: Optional[str] = None,
    depth: int = Query(2, ge=1, le=4),
    min_amount: float = Query(0.0, ge=0),
) -> dict:
    """Nodes/edges payload for the interactive network visualization."""
    return graph_service.build_money_flow(
        db, account_id=account_id, depth=depth, min_amount=min_amount
    )


@router.get("/cycles")
def cycles(db: Session = Depends(get_db)) -> dict:
    """Suspicious circular money-flow patterns (A → B → C → A)."""
    payload = graph_service.build_money_flow(db, depth=3)
    return {
        "cycles": payload["cycles"],
        "total_suspicious": payload["stats"]["suspicious_cycles"],
        "note": "Cycles are detected with NetworkX in the services layer.",
    }


@router.get("/account/{account_id}")
def account_trace(account_id: str, db: Session = Depends(get_db)) -> dict:
    payload = graph_service.trace_account(db, account_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="account not found")
    return payload
