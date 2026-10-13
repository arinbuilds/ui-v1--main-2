"""Deterministic synthetic dataset generator.

Everything here is FICTIONAL demo data (fictional names, fictional entities).
The same generator powers:
  * the demo database (accounts, borrowers, loans, repayments, transactions)
  * the offline training sets for XGBoost / Isolation Forest

so training and serving always see the same data distribution.
Seeded with DEMO_SEED => fully reproducible suspicious cases.
"""
from __future__ import annotations

import datetime as dt
import math

import numpy as np

from app.services.feature_store import (
    CHANNELS,
    MERCHANT_CATEGORIES,
    PURPOSES,
    RELATIONSHIPS,
)

# Fixed demo window — keeps the dataset reproducible across runs.
DATA_START = dt.datetime(2026, 4, 5, 0, 0, 0)
DATA_DAYS = 180
DATA_END = DATA_START + dt.timedelta(days=DATA_DAYS)

CITIES = [
    "Albuquerque", "Phoenix", "Denver", "Austin", "Miami",
    "Chicago", "Seattle", "Boston", "Nashville", "Portland",
]
BANKS = [
    "Cascade Federal", "Sandpiper Bank", "Sandpiper Credit Union",
    "Gray Matter Bank", "Madrigal Trust",
]

# ---------------------------------------------------------------------------
# Accounts — clearly fictional demo entities
# ---------------------------------------------------------------------------
INDIVIDUAL_NAMES = [
    "Walter White", "Jesse Pinkman", "Skyler White", "Hank Schrader",
    "Saul Goodman", "Gus Fring", "Mike Ehrmantraut", "Kim Wexler",
    "Nacho Varga", "Lalo Salamanca", "Hector Salamanca", "Tuco Salamanca",
    "Badger Badger", "Skinny Pete", "Combo Ortiz", "Andrea Cantillo",
    "Brock Cantillo", "Francesca Liddy", "Huell Babineaux", "Patrick Kuby",
    "Tyrus Kitt", "Gale Boetticher", "Marie Schrader", "Wendy S.",
    "Krazy-8 Molina", "No-Doze Rivera", "Emilio Koyama", "Stacey Ehrmantraut",
]

BUSINESS_NAMES = [
    "Los Pollos Hermanos", "Madrigal Logistics", "Gray Matter Technologies",
    "Sandpiper Crossing", "Beneke Freight Solutions", "Purple Sky Consulting",
    "QuickRefund Services", "Cayman Holdings Ltd", "El Dorado Remittance",
    "Nightowl Payments Wallet", "A1 Cab Company", "Tampico Freight",
    "Jesse's Auto Detailing", "Crystal Flash Appliances", "Duck & Cover Storage",
    "Casa Tranquila Realty", "Mesa Verde Credit", "Blue Sky Marketing",
]

LENDER_NAMES = ["Cascade Federal Lending", "Sandpiper Personal Finance"]

# Accounts that exist purely to demonstrate suspicious flow patterns.
ROLE_BY_NAME = {
    "Beneke Freight Solutions": "mule",
    "Purple Sky Consulting": "mule",
    "El Dorado Remittance": "mule",
    "QuickRefund Services": "scam_infra",
    "Cayman Holdings Ltd": "scam_infra",
    "Nightowl Payments Wallet": "scam_infra",
    "Cascade Federal Lending": "lender",
    "Sandpiper Personal Finance": "lender",
}


def build_accounts() -> list[dict]:
    """Deterministic account universe (no RNG)."""
    accounts: list[dict] = []
    idx = 1
    for group, names, entity in (
        (INDIVIDUAL_NAMES, INDIVIDUAL_NAMES, "individual"),
        (BUSINESS_NAMES, BUSINESS_NAMES, "business"),
        (LENDER_NAMES, LENDER_NAMES, "business"),
    ):
        for i, name in enumerate(names):
            accounts.append(
                {
                    "id": f"ACC-{1000 + idx}",
                    "name": name,
                    "entity_type": entity,
                    "bank": BANKS[i % len(BANKS)],
                    "city": CITIES[(i * 3) % len(CITIES)],
                    "role": ROLE_BY_NAME.get(name, "normal"),
                }
            )
            idx += 1
    return accounts


# ---------------------------------------------------------------------------
# Per-account behavioural profiles (used for "normal" activity)
# ---------------------------------------------------------------------------
def build_profiles(accounts: list[dict], rng: np.random.Generator) -> dict[str, dict]:
    profiles: dict[str, dict] = {}
    for acc in accounts:
        is_business = acc["entity_type"] == "business"
        mean_amount = rng.uniform(3000, 18000) if is_business else rng.uniform(350, 6500)
        profiles[acc["id"]] = {
            "daily_rate": rng.uniform(0.35, 0.95) if is_business else rng.uniform(0.45, 1.15),
            "amount_mu": math.log(mean_amount),
            "amount_sigma": rng.uniform(0.35, 0.6),
            "main_city": acc["city"],
            "alt_city": rng.choice([c for c in CITIES if c != acc["city"]]),
            "devices": [f"DEV-{acc['id'][-4:]}-{d}" for d in range(1, rng.integers(2, 4))],
            "channels": list(rng.choice(CHANNELS, size=int(rng.integers(1, 4)), replace=False)),
            "merchants": list(
                rng.choice(MERCHANT_CATEGORIES, size=int(rng.integers(3, 7)), replace=False)
            ),
            "active_start": int(rng.integers(7, 11)),
            "active_end": int(rng.integers(19, 24)),
            "counterparties": [],
            "is_scam_sink": acc["role"] in {"scam_infra", "mule"},
        }
    # known counterparties: everyone transacts regularly with 3-6 others.
    # ~35% of accounts also transact with scam-infrastructure accounts, so those
    # accounts receive a MIX of legitimate and fraudulent inflows (realistic, and
    # it prevents 'previously flagged counterparty' from being a trivial giveaway).
    normal_ids = [a["id"] for a in accounts if a["role"] == "normal"]
    infra_ids = [a["id"] for a in accounts if a["role"] in {"scam_infra", "mule"}]
    for acc in accounts:
        p = profiles[acc["id"]]
        pool = [x for x in normal_ids if x != acc["id"]]
        size = min(len(pool), int(rng.integers(3, 7)))
        chosen = list(rng.choice(pool, size=size, replace=False))
        if acc["role"] == "normal" and infra_ids and rng.random() < 0.55:
            chosen.append(str(rng.choice(infra_ids)))
        p["counterparties"] = chosen
    return profiles


# ---------------------------------------------------------------------------
# Borrowers / loans / repayments
# ---------------------------------------------------------------------------
BORROWER_SCENARIOS = [
    # (scenario, stress) — deterministic spread for the demo narrative
    ("healthy", 0.10), ("healthy", 0.16), ("healthy", 0.22), ("healthy", 0.27),
    ("healthy", 0.31), ("watch", 0.42), ("watch", 0.48), ("watch", 0.53),
    ("stressed", 0.66), ("stressed", 0.74), ("stressed", 0.82), ("stressed", 0.90),
    ("recovering", 0.58), ("healthy", 0.20),
]

LOAN_PURPOSES = ["Business", "Education", "Home", "Vehicle", "Personal", "Medical"]

SPEND_BY_PURPOSE = {
    "Business": {"Business": 0.65, "Essential": 0.2, "Discretionary": 0.1, "Transfer": 0.05},
    "Education": {"Education": 0.6, "Essential": 0.3, "Discretionary": 0.1},
    "Home": {"Essential": 0.7, "Discretionary": 0.2, "Business": 0.1},
    "Vehicle": {"Essential": 0.6, "Discretionary": 0.3, "Transfer": 0.1},
    "Personal": {"Discretionary": 0.45, "Essential": 0.4, "Transfer": 0.15},
    "Medical": {"Essential": 0.85, "Discretionary": 0.15},
}

MERCHANT_BY_SPEND = {
    "Business": ["telecom", "real_estate", "electronics", "general"],
    "Education": ["education", "general"],
    "Investment": ["crypto_exchange", "jewellery", "real_estate"],
    "Essential": ["grocery", "fuel", "utilities", "healthcare", "food"],
    "Discretionary": ["travel", "electronics", "jewellery", "food", "gambling"],
    "Transfer": ["general", "remittance"],
}


def _monthly_series(rng: np.random.Generator, base: float, drift: float) -> list[float]:
    values = []
    level = base * rng.uniform(0.94, 1.06)
    for _ in range(12):
        level = max(level * (1 + drift) + rng.normal(0, base * 0.03), base * 0.3)
        values.append(round(level, 2))
    return values


def generate_borrower(
    rng: np.random.Generator,
    idx: int,
    account: dict,
    stress: float,
    scenario: str = "healthy",
    ref: dt.datetime = DATA_END,
) -> tuple[dict, list[dict], list[dict]]:
    """Generate one borrower with loans + repayment schedule."""
    stress = float(min(max(stress, 0.0), 1.0))
    income = float(rng.lognormal(11.15, 0.32))          # ~₹69k / month
    income = float(np.clip(income, 22000, 320000))

    if scenario == "healthy":
        income_drift = rng.uniform(0.004, 0.02)
        spend_ratio = rng.uniform(0.48, 0.66)
        spend_drift = rng.uniform(-0.01, 0.012)
    elif scenario == "watch":
        income_drift = rng.uniform(-0.03, 0.004)
        spend_ratio = rng.uniform(0.62, 0.78)
        spend_drift = rng.uniform(0.01, 0.045)
    elif scenario == "recovering":
        income_drift = rng.uniform(-0.02, 0.015)
        spend_ratio = rng.uniform(0.6, 0.75)
        spend_drift = rng.uniform(-0.01, 0.02)
    else:  # stressed
        income_drift = rng.uniform(-0.075, -0.015)
        spend_ratio = rng.uniform(0.7, 0.95)
        spend_drift = rng.uniform(0.02, 0.075)

    income_history = _monthly_series(rng, income, income_drift)
    spending_history = _monthly_series(rng, income * spend_ratio, spend_drift)

    employment_years = float(np.clip(rng.normal(6 - 4 * stress, 3.5), 0.2, 30))
    employment_stable = bool(stress < 0.6 and rng.random() > stress * 0.5)

    existing_debt = float(income * 12 * np.clip(rng.normal(0.25 + 1.4 * stress, 0.35), 0, 3.5))
    credit_limit = float(max(income * rng.uniform(1.5, 5.0), 50000))
    credit_utilization = float(np.clip(rng.normal(0.15 + 0.75 * stress, 0.15), 0.02, 0.98))

    borrower = {
        "id": f"BRW-{idx:03d}",
        "account_id": account["id"],
        "name": account["name"],
        "city": account["city"],
        "employer": account["name"] if account["entity_type"] == "business" else f"{account['city']} Regional Hospital"
        if idx % 3 == 0 else f"{account['city']} School District",
        "occupation": "Business owner" if account["entity_type"] == "business" else "Salaried professional",
        "employment_years": round(employment_years, 1),
        "employment_stable": employment_stable,
        "monthly_income": round(income, 2),
        "monthly_spending": round(income * spend_ratio, 2),
        "total_existing_debt": round(existing_debt, 2),
        "credit_limit": round(credit_limit, 2),
        "credit_utilization": round(credit_utilization, 4),
        "income_history": [round(v, 2) for v in income_history],
        "spending_history": [round(v, 2) for v in spending_history],
        "stress": stress,
        "scenario": scenario,
    }

    # ---- loans ----------------------------------------------------------
    n_loans = 1 if rng.random() < 0.65 else 2
    loans: list[dict] = []
    repayments: list[dict] = []
    for li in range(n_loans):
        purpose = LOAN_PURPOSES[int(rng.integers(0, len(LOAN_PURPOSES)))]
        principal = float(
            np.clip(rng.lognormal(12.6, 0.65), 60_000, 4_000_000)
        )
        principal = round(principal / 1000) * 1000
        term = int(rng.choice([12, 18, 24, 36]))
        rate = round(float(rng.uniform(9.0, 18.5)), 2)
        r = rate / 100 / 12
        emi = principal * r * (1 + r) ** term / ((1 + r) ** term - 1)
        months_elapsed = int(rng.integers(3, min(term, 20)))
        disbursed = DATA_END - dt.timedelta(days=30 * months_elapsed + int(rng.integers(0, 20)))
        outstanding = float(np.clip(principal * (1 - months_elapsed / term) * rng.uniform(0.9, 1.08), 0, principal))

        loan = {
            "id": f"LN-{idx:03d}-{li + 1}",
            "borrower_id": borrower["id"],
            "principal": float(principal),
            "outstanding_amount": round(outstanding, 2),
            "purpose": purpose,
            "intended_use": purpose,
            "interest_rate": rate,
            "term_months": term,
            "monthly_emi": round(float(emi), 2),
            "disbursed_at": disbursed,
            "status": "active",
            "stress": stress,
        }

        # ---- repayment schedule ------------------------------------------
        for m in range(1, min(months_elapsed + 2, term) + 1):
            due = disbursed + dt.timedelta(days=30 * m)
            if due > DATA_END + dt.timedelta(days=40):
                continue
            is_future = due > DATA_END
            if is_future:
                status = "upcoming"
                paid_amount, paid_date = 0.0, None
            else:
                u = float(rng.random())
                p_missed = 0.03 + 0.55 * stress
                p_late = 0.05 + 0.35 * stress
                p_partial = 0.02 + 0.28 * stress
                if u < p_missed:
                    status, paid_amount, paid_date = "missed", 0.0, None
                elif u < p_missed + p_late:
                    status = "late"
                    paid_amount = float(emi)
                    paid_date = due + dt.timedelta(days=int(rng.integers(4, 26)))
                elif u < p_missed + p_late + p_partial:
                    status = "partial"
                    paid_amount = round(float(emi) * float(rng.uniform(0.3, 0.7)), 2)
                    paid_date = due + dt.timedelta(days=int(rng.integers(0, 5)))
                else:
                    status = "paid"
                    paid_amount = float(emi)
                    paid_date = due - dt.timedelta(days=int(rng.integers(0, 3)))
            repayments.append(
                {
                    "id": f"RP-{idx:03d}-{li + 1}-{m:02d}",
                    "loan_id": loan["id"],
                    "due_date": due,
                    "paid_date": paid_date,
                    "amount": round(float(emi), 2),
                    "paid_amount": round(paid_amount, 2),
                    "status": status,
                }
            )
        loans.append(loan)
    return borrower, loans, repayments


def generate_borrower_universe(
    rng: np.random.Generator, n: int, accounts: list[dict]
) -> tuple[list[dict], list[dict], list[dict]]:
    """Offline training universe — same generator, never written to the DB."""
    individuals = [a for a in accounts if a["entity_type"] == "individual"]
    borrowers, loans, repayments = [], [], []
    for i in range(n):
        stress = float(rng.beta(1.6, 2.4))          # skewed healthy-ish population
        scenario = (
            "healthy" if stress < 0.4 else "watch" if stress < 0.6 else "stressed"
        )
        acc = individuals[i % len(individuals)]
        b, ls, rs = generate_borrower(
            rng, i + 1, acc, stress, scenario,
            ref=DATA_END,
        )
        b["id"] = f"TRN-{i + 1:05d}"
        for ln in ls:
            ln["borrower_id"] = b["id"]
        borrowers.append(b)
        loans.extend(ls)
        repayments.extend(rs)
    return borrowers, loans, repayments


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------
def _tx(
    ts: dt.datetime,
    sender: str,
    receiver: str,
    amount: float,
    channel: str,
    merchant: str,
    purpose: str,
    relationship: str,
    city: str,
    device: str,
    narrative: str,
    is_fraud: bool = False,
    scam: str | None = None,
    loan_id: str | None = None,
    spend_category: str | None = None,
) -> dict:
    return {
        "ts": ts,
        "sender_account_id": sender,
        "receiver_account_id": receiver,
        "amount": round(float(amount), 2),
        "channel": channel,
        "merchant_category": merchant,
        "purpose": purpose,
        "relationship": relationship,
        "city": city,
        "device_id": device,
        "narrative": narrative,
        "label_is_fraud": is_fraud,
        "label_scam_category": scam,
        "loan_id": loan_id,
        "spend_category": spend_category,
    }


def _normal_transactions(
    accounts: list[dict],
    profiles: dict[str, dict],
    rng: np.random.Generator,
    borrowers_by_account: dict[str, dict],
) -> list[dict]:
    out: list[dict] = []
    rel_pool = ["family", "friend", "business", "merchant", "employer", "unknown"]
    for day in range(DATA_DAYS):
        day_start = DATA_START + dt.timedelta(days=day)
        for acc in accounts:
            p = profiles[acc["id"]]
            if not p["counterparties"]:
                continue
            n = int(rng.poisson(p["daily_rate"]))
            for _ in range(n):
                hour = int(rng.integers(p["active_start"], p["active_end"]))
                minute = int(rng.integers(0, 60))
                ts = day_start + dt.timedelta(hours=hour, minutes=minute)
                if ts >= DATA_END:
                    continue
                receiver = str(rng.choice(p["counterparties"]))
                amount = float(rng.lognormal(p["amount_mu"], p["amount_sigma"]))
                new_counterparty = False

                # behavioural noise (makes the classifier non-trivial)
                if rng.random() < 0.13:
                    hour = int(rng.integers(0, 5))
                    ts = day_start + dt.timedelta(hours=hour, minutes=minute)
                if rng.random() < 0.17:
                    receiver = str(
                        rng.choice([a["id"] for a in accounts if a["id"] != acc["id"]])
                    )
                    new_counterparty = True
                    amount *= rng.uniform(0.5, 1.6)
                city = p["main_city"] if rng.random() < 0.86 else p["alt_city"]
                device = str(rng.choice(p["devices"]))
                if rng.random() < 0.07:
                    device = f"DEV-NEW-{int(rng.integers(100, 999))}"

                borrower = borrowers_by_account.get(acc["id"])
                if borrower is not None and amount > borrower["monthly_income"] * 0.9:
                    amount = borrower["monthly_income"] * rng.uniform(0.1, 0.6)
                # people often send round sums — keeps 'round amount' from being
                # a perfect fraud giveaway
                if rng.random() < 0.30:
                    amount = float(np.round(amount / 100.0) * 100.0)

                out.append(
                    _tx(
                        ts, acc["id"], receiver, amount,
                        channel=str(rng.choice(p["channels"])),
                        merchant=str(rng.choice(p["merchants"])),
                        purpose=str(rng.choice(PURPOSES)),
                        relationship=str(rng.choice(rel_pool)),
                        city=city, device=device,
                        narrative="Routine payment",
                    )
                )
    return out


def _fraud_transactions(
    accounts: list[dict],
    profiles: dict[str, dict],
    rng: np.random.Generator,
) -> list[dict]:
    out: list[dict] = []
    individuals = [a for a in accounts if a["entity_type"] == "individual"]
    normals = [a for a in accounts if a["role"] == "normal"]
    sinks = {r: [a for a in accounts if a["role"] == r] for r in ("scam_infra", "mule")}

    def night_ts(day: int) -> dt.datetime:
        return DATA_START + dt.timedelta(
            days=int(day), hours=int(rng.integers(0, 5)), minutes=int(rng.integers(0, 60))
        )

    def day_ts(day: int) -> dt.datetime:
        return DATA_START + dt.timedelta(
            days=int(day), hours=int(rng.integers(8, 22)), minutes=int(rng.integers(0, 60))
        )

    # 1) PHISHING — night, brand-new payee, odd city, round high amount
    for _ in range(70):
        victim = individuals[int(rng.integers(0, len(individuals)))]
        sink = sinks["scam_infra"][int(rng.integers(0, len(sinks["scam_infra"])))]
        day = int(rng.integers(10, DATA_DAYS - 5))
        amount = float(np.round(rng.uniform(8000, 90000) / 100) * 100)
        out.append(
            _tx(
                night_ts(day), victim["id"], sink["id"], amount,
                channel="upi",
                merchant=str(rng.choice(["general", "telecom", "utilities", "grocery", "electronics"])),
                purpose=str(rng.choice(["transfer", "bill_payment", "gift", "purchase"])),
                relationship="unknown",
                city=str(rng.choice(CITIES)),
                device=f"DEV-NEW-{int(rng.integers(1000, 9999))}",
                narrative="KYC re-verification fee — account will be blocked",
                is_fraud=True, scam="phishing",
            )
        )

    # 2) CIRCULAR MONEY FLOW — A → B → C → A (layering)
    for c in range(15):
        pool = [a for a in normals]
        i = int(rng.integers(0, len(pool)))
        a = pool[i]
        b = sinks["mule"][(c + 1) % len(sinks["mule"])]
        c_acc = pool[(i + 5 + c) % len(pool)]
        if c_acc["id"] == a["id"]:
            c_acc = pool[(i + 7) % len(pool)]
        day = int(rng.integers(20, DATA_DAYS - 6))
        base = float(np.round(rng.uniform(40000, 240000) / 500) * 500)
        t0 = day_ts(day)
        legs = [
            (a, b, base, t0),
            (b, c_acc, base * 0.995, t0 + dt.timedelta(hours=3)),
            (c_acc, a, base * 0.985, t0 + dt.timedelta(hours=7)),
        ]
        for src, dst, amt, ts in legs:
            out.append(
                _tx(
                    ts, src["id"], dst["id"], amt,
                    channel="netbanking",
                    merchant=str(rng.choice(["general", "electronics", "remittance", "real_estate"])),
                    purpose=str(rng.choice(["transfer", "purchase", "investment"])),
                    relationship="business", city=src["city"],
                    device=profiles[src["id"]]["devices"][0],
                    narrative="Round-trip settlement — circular flow",
                    is_fraud=True, scam="mule_account",
                )
            )

    # 3) INVESTMENT SCAM — large round sums to an offshore-style entity
    for _ in range(40):
        victim = individuals[int(rng.integers(0, len(individuals)))]
        sink = sinks["scam_infra"][int(rng.integers(0, len(sinks["scam_infra"])))]
        day = int(rng.integers(15, DATA_DAYS - 4))
        amount = float(np.round(rng.uniform(50000, 500000) / 10000) * 10000)
        out.append(
            _tx(
                day_ts(day), victim["id"], sink["id"], amount,
                channel="netbanking", merchant="crypto_exchange", purpose="investment",
                relationship="business", city=profiles[victim["id"]]["main_city"],
                device=profiles[victim["id"]]["devices"][0],
                narrative="Tranche investment — guaranteed 18% monthly return",
                is_fraud=True, scam="investment_scam",
            )
        )

    # 4) FAKE REFUND — small lure credit then a "processing fee" outflow
    for _ in range(30):
        victim = individuals[int(rng.integers(0, len(individuals)))]
        sink = sinks["scam_infra"][int(rng.integers(0, len(sinks["scam_infra"])))]
        day = int(rng.integers(25, DATA_DAYS - 8))
        out.append(
            _tx(  # lure — anomalous but NOT labelled fraud
                day_ts(day), sink["id"], victim["id"], float(rng.uniform(1500, 4500)),
                channel="upi", merchant="general", purpose="refund",
                relationship="merchant", city=profiles[victim["id"]]["main_city"],
                device=profiles[victim["id"]]["devices"][0],
                narrative="Refund credited — confirm details",
            )
        )
        out.append(
            _tx(
                day_ts(day) + dt.timedelta(hours=2), victim["id"], sink["id"],
                float(np.round(rng.uniform(6000, 40000) / 100) * 100),
                channel="upi",
                merchant=str(rng.choice(["general", "food", "electronics", "travel"])),
                purpose="refund",
                relationship="merchant", city=str(rng.choice(CITIES)),
                device=f"DEV-NEW-{int(rng.integers(1000, 9999))}",
                narrative="Refund processing fee / GST verification",
                is_fraud=True, scam="fake_refund",
            )
        )

    # 5) PAYMENT-REQUEST SCAM — repeated small collect requests
    for _ in range(50):
        victim = individuals[int(rng.integers(0, len(individuals)))]
        sink = sinks["scam_infra"][int(rng.integers(0, len(sinks["scam_infra"])))]
        day = int(rng.integers(30, DATA_DAYS - 10))
        n = int(rng.integers(2, 5))
        for k in range(n):                out.append(
                    _tx(
                        day_ts(day + k) + dt.timedelta(hours=int(rng.integers(20, 23))),
                        victim["id"], sink["id"], float(rng.uniform(499, 2499)),
                        channel="upi",
                        merchant=str(rng.choice(["general", "telecom", "utilities", "food"])),
                        purpose=str(rng.choice(["transfer", "bill_payment", "gift"])),
                        relationship="unknown", city=profiles[victim["id"]]["main_city"],
                    device=f"DEV-NEW-{int(rng.integers(1000, 9999))}",
                    narrative="UPI collect request accepted — loan EMI clearance",
                    is_fraud=True, scam="payment_request_scam",
                )
            )

    # 6) IMPERSONATION — urgent "relative" transfer at odd hour
    for _ in range(45):
        victim = individuals[int(rng.integers(0, len(individuals)))]
        impostor = individuals[int(rng.integers(0, len(individuals)))]
        if impostor["id"] == victim["id"]:
            continue
        day = int(rng.integers(12, DATA_DAYS - 4))
        out.append(
            _tx(
                night_ts(day), victim["id"], impostor["id"],
                float(np.round(rng.uniform(15000, 250000) / 500) * 500),
                channel="wallet",
                merchant=str(rng.choice(["general", "grocery", "healthcare", "food"])),
                purpose=str(rng.choice(["transfer", "gift"])),
                relationship="family", city=str(rng.choice(CITIES)),
                device=f"DEV-NEW-{int(rng.integers(1000, 9999))}",
                narrative="Emergency — I'm stuck, send cash now (new number)",
                is_fraud=True, scam="impersonation",
            )
        )

    # 7) MULE FAN-IN / FAN-OUT — many senders, one aggregator, fast dispersal
    for round_i in range(20):
        mule = sinks["mule"][round_i % len(sinks["mule"])]
        day = int(rng.integers(40, DATA_DAYS - 6))
        t0 = day_ts(day)
        sources = list(rng.choice(normals, size=int(rng.integers(3, 6)), replace=False))
        for s_i, src in enumerate(sources):                out.append(
                    _tx(
                        t0 + dt.timedelta(minutes=int(rng.integers(0, 120))),
                        src["id"], mule["id"], float(np.round(rng.uniform(20000, 150000) / 100) * 100),
                        channel=str(rng.choice(["upi", "wallet", "card"])),
                        merchant=str(rng.choice(["general", "electronics", "remittance", "food"])),
                        purpose=str(rng.choice(["transfer", "purchase", "bill_payment"])),
                        relationship="business", city=str(rng.choice(CITIES)),
                    device=f"DEV-NEW-{int(rng.integers(1000, 9999))}",
                    narrative=f"Trade settlement batch {round_i + 1}",
                    is_fraud=True, scam="mule_account",
                )
            )
        out.append(
            _tx(
                t0 + dt.timedelta(hours=2),
                mule["id"], sinks["scam_infra"][round_i % len(sinks["scam_infra"])]["id"],
                float(np.round(rng.uniform(60000, 400000) / 100) * 100),
                channel="netbanking",
                merchant=str(rng.choice(["general", "remittance", "real_estate"])),
                purpose=str(rng.choice(["transfer", "investment", "purchase"])),
                relationship="business", city=mule["city"],
                device=profiles[mule["id"]]["devices"][0],
                narrative="Consolidated outward remittance",
                is_fraud=True, scam="mule_account",
            )
        )
    return out


def _loan_transactions(
    loans: list[dict],
    borrowers: dict[str, dict],
    accounts: list[dict],
    lender_ids: list[str],
    profiles: dict[str, dict],
    rng: np.random.Generator,
) -> list[dict]:
    out: list[dict] = []
    for i, loan in enumerate(loans):
        b = borrowers[loan["borrower_id"]]
        acc_id = b["account_id"]
        lender = lender_ids[i % len(lender_ids)]
        p = profiles[acc_id]
        disbursed: dt.datetime = loan["disbursed_at"]

        # disbursement inflow
        out.append(
            _tx(
                disbursed + dt.timedelta(hours=11), lender, acc_id, loan["principal"],
                channel="netbanking", merchant="general", purpose="transfer",
                relationship="lender", city=b["city"], device=p["devices"][0],
                narrative=f"Loan disbursed — {loan['purpose']} loan {loan['id']}",
                loan_id=loan["id"],
            )
        )

        # subsequent spending, classified into broad categories
        weights = SPEND_BY_PURPOSE.get(loan["purpose"], SPEND_BY_PURPOSE["Personal"])
        cats = list(weights.keys())
        probs = np.array([weights[c] for c in cats], dtype=float)
        probs = probs / probs.sum()
        n_spend = int(rng.integers(5, 11))
        counter = [a["id"] for a in accounts if a["role"] == "normal" and a["id"] != acc_id]
        for k in range(n_spend):
            cat = str(rng.choice(cats, p=probs))
            ts = disbursed + dt.timedelta(days=int(rng.integers(1, 70)), hours=int(rng.integers(9, 21)))
            if ts >= DATA_END:
                continue
            out.append(
                _tx(
                    ts, acc_id, str(rng.choice(counter)),
                    float(np.clip(rng.lognormal(9.2, 0.8), 700, 250000)),
                    channel=str(rng.choice(p["channels"])),
                    merchant=str(rng.choice(MERCHANT_BY_SPEND.get(cat, ["general"]))),
                    purpose="purchase",
                    relationship="business" if cat == "Business" else "merchant",
                    city=p["main_city"], device=str(rng.choice(p["devices"])),
                    narrative=f"{cat} spend against {loan['purpose']} loan",
                    loan_id=loan["id"], spend_category=cat,
                )
            )

        # repayment outflows
        for m in range(1, 13):
            due = disbursed + dt.timedelta(days=30 * m)
            if due >= DATA_END:
                break
            out.append(
                _tx(
                    due + dt.timedelta(hours=10), acc_id, lender, loan["monthly_emi"],
                    channel="netbanking", merchant="general", purpose="loan_repayment",
                    relationship="lender", city=b["city"], device=p["devices"][0],
                    narrative=f"EMI repayment — {loan['id']}",
                    loan_id=loan["id"],
                )
            )
    return out


def generate_transaction_pool(
    seed: int,
    n_extra_borrowers: int = 0,
) -> dict:
    """Generate the complete deterministic demo dataset (accounts, borrowers,
    loans, repayments, transactions with ground-truth labels)."""
    rng = np.random.default_rng(seed)
    accounts = build_accounts()
    profiles = build_profiles(accounts, rng)

    # ---- borrowers -------------------------------------------------------
    individuals = [a for a in accounts if a["entity_type"] == "individual"]
    borrowers: list[dict] = []
    loans: list[dict] = []
    repayments: list[dict] = []
    for i, (scenario, stress) in enumerate(BORROWER_SCENARIOS):
        acc = individuals[i]
        b, ls, rs = generate_borrower(rng, i + 1, acc, stress, scenario)
        borrowers.append(b)
        loans.extend(ls)
        repayments.extend(rs)

    borrowers_by_account = {b["account_id"]: b for b in borrowers}

    # ---- transactions ----------------------------------------------------
    txs: list[dict] = []
    txs.extend(_normal_transactions(accounts, profiles, rng, borrowers_by_account))
    txs.extend(_fraud_transactions(accounts, profiles, rng))
    lender_ids = [a["id"] for a in accounts if a["role"] == "lender"]
    txs.extend(_loan_transactions(loans, {b["id"]: b for b in borrowers}, accounts, lender_ids, profiles, rng))

    txs = [t for t in txs if t["ts"] < DATA_END]

    # Camouflage: a share of fraudulent transactions deliberately blends into the
    # sender's normal pattern (hour, device, city and even amount), so the
    # classifier must combine signals instead of learning one trivial rule.
    for t in txs:
        if not t["label_is_fraud"]:
            continue
        if rng.random() >= 0.50:
            continue
        p = profiles.get(t["sender_account_id"])
        if not p:
            continue
        if t["label_scam_category"] != "investment_scam" and rng.random() < 0.35:
            # blend the amount into the sender's normal band (low-value probing)
            typical = math.exp(p["amount_mu"])
            t["amount"] = round(max(typical * float(rng.uniform(0.5, 3.0)), 200.0), 2)
        if rng.random() < 0.80:
            t["device_id"] = str(rng.choice(p["devices"]))
        if rng.random() < 0.65:
            t["city"] = p["main_city"]
        if rng.random() < 0.55:
            t["ts"] = t["ts"].replace(
                hour=int(rng.integers(9, 20)), minute=int(rng.integers(0, 60))
            )

    txs.sort(key=lambda t: (t["ts"], t["sender_account_id"], t["amount"]))

    # counterparty_is_new is defined chronologically (no leakage)
    seen_pairs: set[tuple[str, str]] = set()
    for t in txs:
        pair = (t["sender_account_id"], t["receiver_account_id"])
        t["counterparty_is_new"] = pair not in seen_pairs
        seen_pairs.add(pair)
        t["id"] = ""  # assigned by the seeder after flush

    return {
        "accounts": accounts,
        "profiles": profiles,
        "borrowers": borrowers,
        "loans": loans,
        "repayments": repayments,
        "transactions": txs,
    }
