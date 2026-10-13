"""NetworkX money-flow graph analysis.

Nodes  = accounts / businesses
Edges  = aggregated transactions (amount, timestamps, per-transaction ids)

Suspicious circular flow (A → B → C → A) is detected here with NetworkX +
bounded DFS.  React only renders the returned payload — all graph processing
happens in this service.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import networkx as nx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Account, Borrower, Transaction

MAX_CYCLE_LEN = 5
MAX_CYCLES = 40


def _load_transactions(db: Session) -> list[dict]:
    rows = db.execute(
        select(
            Transaction.id,
            Transaction.sender_account_id,
            Transaction.receiver_account_id,
            Transaction.amount,
            Transaction.ts,
            Transaction.fraud_score,
            Transaction.is_anomaly,
            Transaction.scam_category,
            Transaction.channel,
        ).order_by(Transaction.ts)
    ).all()
    return [
        {
            "id": r[0],
            "sender": r[1],
            "receiver": r[2],
            "amount": float(r[3]),
            "ts": r[4],
            "fraud_score": float(r[5]) if r[5] is not None else None,
            "is_anomaly": bool(r[6]) if r[6] is not None else False,
            "scam_category": r[7],
            "channel": r[8],
        }
        for r in rows
    ]


def _accounts(db: Session) -> dict[str, dict]:
    return {
        a.id: {
            "id": a.id,
            "label": a.name,
            "entity_type": a.entity_type,
            "bank": a.bank,
            "city": a.city,
            "role": a.role,
        }
        for a in db.scalars(select(Account)).all()
    }


def _borrower_scores(db: Session) -> dict[str, dict]:
    out = {}
    for b in db.scalars(select(Borrower)).all():
        out[b.account_id] = {
            "borrower_id": b.id,
            "borrower_name": b.name,
            "repayment_score": b.repayment_score,
            "repayment_category": b.repayment_category,
        }
    return out


# ---------------------------------------------------------------------------
# graph construction
# ---------------------------------------------------------------------------
def _aggregate(txs: list[dict]) -> dict[tuple[str, str], dict]:
    edges: dict[tuple[str, str], dict] = {}
    for t in txs:
        key = (t["sender"], t["receiver"])
        e = edges.get(key)
        if e is None:
            edges[key] = {
                "source": t["sender"],
                "target": t["receiver"],
                "amount": t["amount"],
                "count": 1,
                "first_ts": t["ts"],
                "last_ts": t["ts"],
                "tx_ids": [t["id"]],
                "max_fraud_score": t["fraud_score"] or 0.0,
                "anomaly_count": 1 if t["is_anomaly"] else 0,
            }
        else:
            e["amount"] += t["amount"]
            e["count"] += 1
            e["last_ts"] = t["ts"]
            e["tx_ids"].append(t["id"])
            e["max_fraud_score"] = max(e["max_fraud_score"], t["fraud_score"] or 0.0)
            e["anomaly_count"] += 1 if t["is_anomaly"] else 0
    return edges


def find_cycles(graph: nx.DiGraph, max_len: int = MAX_CYCLE_LEN, limit: int = MAX_CYCLES) -> list[list[str]]:
    """Bounded DFS cycle enumeration; each cycle reported once (its lowest-id
    node is the search root)."""
    cycles: list[list[str]] = []
    for start in sorted(graph.nodes()):
        stack: list[tuple[str, list[str]]] = [(start, [start])]
        while stack:
            node, path = stack.pop()
            if len(path) > max_len:
                continue
            for nxt in graph.successors(node):
                if nxt == start and len(path) >= 3:
                    cycles.append(path[:])
                    if len(cycles) >= limit:
                        return cycles
                elif nxt not in path and nxt > start:
                    stack.append((nxt, path + [nxt]))
    return cycles


def _score_cycle(
    cycle: list[str], edge_data: dict[tuple[str, str], dict]
) -> dict:
    keys = [(cycle[i], cycle[(i + 1) % len(cycle)]) for i in range(len(cycle))]
    keys = [k for k in keys if k in edge_data]
    if not keys:
        return {"suspicious": False, "total_amount": 0.0, "duration_hours": 0.0}

    total = sum(edge_data[k]["amount"] for k in keys)
    first = min(edge_data[k]["first_ts"] for k in keys)
    last = max(edge_data[k]["last_ts"] for k in keys)
    duration_hours = (last - first).total_seconds() / 3600.0
    max_fraud = max(edge_data[k]["max_fraud_score"] for k in keys)

    reasons = []
    if duration_hours <= 168 and total >= 30000:
        reasons.append(
            f"₹{total:,.0f} returned to the origin within {duration_hours:.0f} hours"
        )
    if max_fraud >= 61:
        reasons.append("at least one leg carries a high fraud-risk score")
    if len(cycle) <= 4 and duration_hours <= 336 and total >= 15000:
        reasons.append("short round-trip pattern typical of layering")

    suspicious = bool(reasons)
    tightness = max(0.0, 1.0 - duration_hours / 168.0)
    score = min(100.0, 30 * len(reasons) + 40 * tightness + min(total / 20000.0, 30))
    return {
        "suspicious": suspicious,
        "total_amount": round(total, 2),
        "duration_hours": round(duration_hours, 1),
        "max_fraud_score": round(max_fraud, 1),
        "reasons": reasons,
        "cycle_score": round(score, 1),
        "edges": [f"{a}->{b}" for a, b in keys],
    }


def build_money_flow(
    db: Session,
    account_id: str | None = None,
    depth: int = 2,
    min_amount: float = 0.0,
) -> dict:
    accounts = _accounts(db)
    borrowers = _borrower_scores(db)
    txs = _load_transactions(db)
    if min_amount > 0:
        txs = [t for t in txs if t["amount"] >= min_amount]
    edge_data = _aggregate(txs)

    graph = nx.DiGraph()
    for key, e in edge_data.items():
        graph.add_edge(*key)

    # ---- cycles (computed on the full graph, then filtered) --------------
    raw_cycles = find_cycles(graph)
    cycles = []
    for cyc in raw_cycles:
        info = _score_cycle(cyc, edge_data)
        info["nodes"] = cyc
        info["labels"] = [accounts.get(n, {}).get("label", n) for n in cyc]
        cycles.append(info)
    cycles.sort(key=lambda c: (c["suspicious"], c["cycle_score"]), reverse=True)

    suspicious_edge_keys = {k for c in cycles if c["suspicious"] for k in c.get("edges", [])}

    # ---- node neighbourhood ---------------------------------------------
    nodes = set(graph.nodes())
    if account_id and account_id in graph:
        frontier = {account_id}
        seen = {account_id}
        for _ in range(max(1, depth)):
            nxt = set()
            for n in frontier:
                nxt |= set(graph.successors(n)) | set(graph.predecessors(n))
            nxt -= seen
            seen |= nxt
            frontier = nxt
        nodes = seen

    # node aggregates
    in_total: dict[str, float] = defaultdict(float)
    out_total: dict[str, float] = defaultdict(float)
    tx_count: dict[str, int] = defaultdict(int)
    out_risk: dict[str, float] = defaultdict(float)
    anomaly_count: dict[str, int] = defaultdict(int)
    for t in txs:
        out_total[t["sender"]] += t["amount"]
        in_total[t["receiver"]] += t["amount"]
        tx_count[t["sender"]] += 1
        tx_count[t["receiver"]] += 1
        if t["fraud_score"] is not None:
            out_risk[t["sender"]] = max(out_risk[t["sender"]], t["fraud_score"])
        anomaly_count[t["sender"]] += 1 if t["is_anomaly"] else 0

    node_payload = []
    for n in sorted(nodes):
        meta = accounts.get(n, {"id": n, "label": n, "entity_type": "unknown", "role": "normal"})
        b = borrowers.get(n, {})
        node_payload.append(
            {
                **meta,
                "in_total": round(in_total.get(n, 0.0), 2),
                "out_total": round(out_total.get(n, 0.0), 2),
                "tx_count": tx_count.get(n, 0),
                "fraud_risk": round(out_risk.get(n, 0.0), 1),
                "anomaly_count": anomaly_count.get(n, 0),
                "selected": bool(account_id and n == account_id),
                **b,
            }
        )

    edge_payload = []
    for key, e in edge_data.items():
        if key[0] not in nodes or key[1] not in nodes:
            continue
        edge_key = f"{key[0]}->{key[1]}"
        in_suspicious_cycle = edge_key in suspicious_edge_keys
        edge_payload.append(
            {
                "id": edge_key,
                "source": key[0],
                "target": key[1],
                "amount": round(e["amount"], 2),
                "count": e["count"],
                "first_ts": e["first_ts"].isoformat(),
                "last_ts": e["last_ts"].isoformat(),
                "max_fraud_score": round(e["max_fraud_score"], 1),
                "anomaly_count": e["anomaly_count"],
                "in_suspicious_cycle": in_suspicious_cycle,
                # cap so the inspector payload stays small
                "tx_ids": e["tx_ids"][:25],
            }
        )
    edge_payload.sort(key=lambda e: e["amount"], reverse=True)

    selected_cycles = [
        c for c in cycles if not account_id or account_id in c["nodes"]
    ][:12]

    return {
        "nodes": node_payload,
        "edges": edge_payload,
        "cycles": selected_cycles,
        "stats": {
            "node_count": len(node_payload),
            "edge_count": len(edge_payload),
            "total_flow": round(sum(e["amount"] for e in edge_payload), 2),
            "suspicious_cycles": sum(1 for c in cycles if c["suspicious"]),
            "accounts_with_anomalies": sum(1 for n in node_payload if n["anomaly_count"] > 0),
            "root_account": account_id,
            "depth": depth,
        },
    }


# ---------------------------------------------------------------------------
# single-account trace
# ---------------------------------------------------------------------------
def trace_account(db: Session, account_id: str, limit: int = 12) -> dict | None:
    accounts = _accounts(db)
    if account_id not in accounts:
        return None
    txs = [t for t in _load_transactions(db) if account_id in (t["sender"], t["receiver"])]
    txs.sort(key=lambda t: t["ts"], reverse=True)

    incoming: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})
    outgoing: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})
    for t in txs:
        if t["receiver"] == account_id:
            incoming[t["sender"]]["total"] += t["amount"]
            incoming[t["sender"]]["count"] += 1
        else:
            outgoing[t["receiver"]]["total"] += t["amount"]
            outgoing[t["receiver"]]["count"] += 1

    def _ranked(mapping, reverse=False):
        items = [
            {
                "account_id": k,
                "name": accounts.get(k, {}).get("label", k),
                "total": round(v["total"], 2),
                "count": v["count"],
            }
            for k, v in mapping.items()
        ]
        items.sort(key=lambda x: x["total"], reverse=True)
        return items[:limit]

    graph_flow = build_money_flow(db, account_id=account_id, depth=1)
    related_cycles = [c for c in graph_flow["cycles"] if account_id in c["nodes"]]

    return {
        "account": accounts[account_id],
        "in_total": round(sum(v["total"] for v in incoming.values()), 2),
        "out_total": round(sum(v["total"] for v in outgoing.values()), 2),
        "tx_count": len(txs),
        "incoming": _ranked(incoming),
        "outgoing": _ranked(outgoing),
        "connected_accounts": sorted(set(incoming) | set(outgoing)),
        "recent_transactions": [
            {
                "id": t["id"],
                "counterparty": accounts.get(
                    t["receiver"] if t["sender"] == account_id else t["sender"], {}
                ).get("label", "?"),
                "direction": "in" if t["receiver"] == account_id else "out",
                "amount": t["amount"],
                "ts": t["ts"].isoformat(),
                "channel": t["channel"],
                "fraud_score": t["fraud_score"],
                "is_anomaly": t["is_anomaly"],
                "scam_category": t["scam_category"],
            }
            for t in txs[:limit]
        ],
        "cycles": related_cycles,
    }
