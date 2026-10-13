"""Feature engineering for the Services/ML layer.

The exact same builders are used for offline training and online inference so
that training/serving skew is impossible.  Nothing in React ever computes
features — this module is the only place feature vectors are constructed.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter, defaultdict

import numpy as np

# ---------------------------------------------------------------------------
# Fixed vocabularies (deterministic category encoding — no one-hot drift)
# ---------------------------------------------------------------------------
CHANNELS = ["upi", "wallet", "card", "netbanking"]
MERCHANT_CATEGORIES = [
    "grocery", "electronics", "food", "travel", "fuel", "jewellery",
    "real_estate", "education", "healthcare", "remittance", "gambling",
    "crypto_exchange", "telecom", "utilities", "general",
]
PURPOSES = [
    "purchase", "transfer", "salary", "rent", "loan_repayment",
    "investment", "bill_payment", "gift", "refund",
]
RELATIONSHIPS = [
    "family", "friend", "business", "merchant", "lender", "employer", "unknown",
]

# ---------------------------------------------------------------------------
# Transaction feature vector
# ---------------------------------------------------------------------------
FEATURE_NAMES_TX: list[str] = [
    "log_amount",
    "amount_ratio_mean",
    "amount_ratio_p90",
    "amount_zscore",
    "hour_of_day",
    "is_night",
    "is_weekend",
    "channel_code",
    "merchant_code",
    "purpose_code",
    "relationship_code",
    "counterparty_is_new",
    "geo_deviation",
    "device_change",
    "tx_count_24h",
    "tx_count_7d",
    "amount_sum_7d_log",
    "hours_since_last",
    "avg_interval_hours",
    "log_user_mean_amount",
    "counterparty_tx_count",
    "counterparty_prior_fraud_rate",
    "receiver_unique_senders",
    "receiver_in_tx_count",
    "receiver_fraud_rate",
    "receiver_in_amount_7d_log",
    "is_round_amount",
    "amount_over_receiver_avg",
]

# ---------------------------------------------------------------------------
# Borrower / repayment feature vector
# ---------------------------------------------------------------------------
FEATURE_NAMES_BORROWER: list[str] = [
    "log_outstanding",
    "monthly_emi",
    "emi_to_income",
    "loan_to_income",
    "on_time_ratio",
    "missed_payments",
    "late_payments",
    "partial_payments",
    "recent_delinquency_30d",
    "log_income",
    "income_trend",
    "income_volatility",
    "employment_years",
    "employment_stable",
    "existing_debt",
    "debt_to_income",
    "credit_utilization",
    "spending_trend",
    "spending_to_income",
    "active_loans",
    "avg_utilisation_pct",
    "months_since_disbursement",
]


def _code(value, vocab: list[str]) -> float:
    try:
        return float(vocab.index(value))
    except ValueError:
        return -1.0


def _as_float(x) -> float:
    v = float(x)
    if v != v:  # NaN
        return 0.0
    return v


class TransactionFeatureBuilder:
    """Stateful, chronological feature builder.

    `transform()` only reads state built from transactions that occurred
    strictly earlier, so there is no label/time leakage between training and
    inference.
    """

    def __init__(self) -> None:
        self._sender_history: dict[str, list[dict]] = defaultdict(list)
        self._pair_count: Counter = Counter()
        self._pair_fraud: Counter = Counter()
        self._receiver_senders: dict[str, set] = defaultdict(set)
        self._receiver_in_count: Counter = Counter()
        self._receiver_fraud: Counter = Counter()
        self._receiver_flows: dict[str, list[tuple[dt.datetime, float]]] = defaultdict(list)
        self._receiver_amounts: dict[str, list[float]] = defaultdict(list)

    # -- read -------------------------------------------------------------
    def transform(self, tx: dict) -> list[float]:
        sender = tx["sender_account_id"]
        receiver = tx["receiver_account_id"]
        amount = float(tx["amount"])
        ts: dt.datetime = tx["ts"]

        hist = self._sender_history.get(sender, [])
        amounts = [h["amount"] for h in hist]

        if amounts:
            mean_amt = float(np.mean(amounts))
            std_amt = float(np.std(amounts)) or 1.0
            p90 = float(np.percentile(amounts, 90))
        else:
            mean_amt = std_amt = p90 = amount

        # amount context
        log_amount = float(np.log1p(amount))
        amount_ratio_mean = amount / (mean_amt + 1.0)
        amount_ratio_p90 = amount / (p90 + 1.0)
        amount_zscore = float(np.clip((amount - mean_amt) / (std_amt + 1.0), -5, 5))

        # timing
        hour = ts.hour + ts.minute / 60.0
        is_night = 1.0 if (hour < 6.0 or hour >= 23.0) else 0.0
        is_weekend = 1.0 if ts.weekday() >= 5 else 0.0

        # categorical codes
        channel_code = _code(tx.get("channel"), CHANNELS)
        merchant_code = _code(tx.get("merchant_category"), MERCHANT_CATEGORIES)
        purpose_code = _code(tx.get("purpose"), PURPOSES)
        relationship_code = _code(tx.get("relationship"), RELATIONSHIPS)

        # counterparty context
        pair_key = (sender, receiver)
        pair_count = self._pair_count.get(pair_key, 0)
        counterparty_is_new = 1.0 if pair_count == 0 else 0.0
        prior_fraud = self._pair_fraud.get(pair_key, 0)
        # smoothed so a single historical flag is evidence, not a verdict
        counterparty_prior_fraud_rate = prior_fraud / (pair_count + 5)

        # behavioural deviation
        if hist:
            usual_cities = Counter(h["city"] for h in hist[-20:])
            geo_deviation = 0.0 if tx.get("city") == usual_cities.most_common(1)[0][0] else 1.0
            known_devices = {h["device"] for h in hist[-10:]}
            device_change = 0.0 if tx.get("device_id") in known_devices else 1.0
            last_ts = hist[-1]["ts"]
            hours_since_last = min((ts - last_ts).total_seconds() / 3600.0, 720.0)
            if len(hist) >= 2:
                gaps = [
                    (hist[i]["ts"] - hist[i - 1]["ts"]).total_seconds() / 3600.0
                    for i in range(1, len(hist))
                ]
                avg_interval = float(np.mean(gaps))
            else:
                avg_interval = 0.0
            log_user_mean = float(np.log1p(mean_amt))
        else:
            geo_deviation = 0.0   # unknown — new sender, no baseline yet
            device_change = 0.0
            hours_since_last = 720.0
            avg_interval = 0.0
            log_user_mean = float(np.log1p(amount))

        cutoff_24h = ts - dt.timedelta(hours=24)
        cutoff_7d = ts - dt.timedelta(days=7)
        tx_count_24h = sum(1 for h in hist if h["ts"] >= cutoff_24h)
        tx_count_7d = sum(1 for h in hist if h["ts"] >= cutoff_7d)
        amount_sum_7d = sum(h["amount"] for h in hist if h["ts"] >= cutoff_7d)

        # receiver (counterparty) graph-ish context
        receiver_in_count = self._receiver_in_count.get(receiver, 0)
        receiver_unique_senders = len(self._receiver_senders.get(receiver, set()))
        receiver_fraud_rate = self._receiver_fraud.get(receiver, 0) / (receiver_in_count + 5)
        flows = self._receiver_flows.get(receiver, [])
        in_sum_7d = sum(a for t, a in flows if t >= cutoff_7d)
        recv_amounts = self._receiver_amounts.get(receiver, [])
        receiver_avg = float(np.mean(recv_amounts)) if recv_amounts else amount
        amount_over_receiver_avg = amount / (receiver_avg + 1.0)

        is_round_amount = 1.0 if abs(amount % 100.0) < 1e-6 else 0.0

        return [
            log_amount,
            _as_float(amount_ratio_mean),
            _as_float(amount_ratio_p90),
            amount_zscore,
            hour,
            is_night,
            is_weekend,
            channel_code,
            merchant_code,
            purpose_code,
            relationship_code,
            counterparty_is_new,
            geo_deviation,
            device_change,
            float(tx_count_24h),
            float(tx_count_7d),
            float(np.log1p(amount_sum_7d)),
            hours_since_last,
            avg_interval,
            log_user_mean,
            float(pair_count),
            _as_float(counterparty_prior_fraud_rate),
            float(receiver_unique_senders),
            float(receiver_in_count),
            _as_float(receiver_fraud_rate),
            float(np.log1p(in_sum_7d)),
            is_round_amount,
            _as_float(amount_over_receiver_avg),
        ]

    # -- write ------------------------------------------------------------
    def update(self, tx: dict, label_is_fraud: bool = False) -> None:
        sender = tx["sender_account_id"]
        receiver = tx["receiver_account_id"]
        self._sender_history[sender].append(
            {
                "ts": tx["ts"],
                "amount": float(tx["amount"]),
                "city": tx.get("city") or "unknown",
                "device": tx.get("device_id") or "unknown",
                "receiver": receiver,
            }
        )
        pair_key = (sender, receiver)
        self._pair_count[pair_key] += 1
        if label_is_fraud:
            self._pair_fraud[pair_key] += 1
        self._receiver_senders[receiver].add(sender)
        self._receiver_in_count[receiver] += 1
        if label_is_fraud:
            self._receiver_fraud[receiver] += 1
        self._receiver_flows[receiver].append((tx["ts"], float(tx["amount"])))
        self._receiver_amounts[receiver].append(float(tx["amount"]))

    def transform_many(self, txs: list[dict], labels: list[bool] | None = None) -> np.ndarray:
        """Chronological pass — features for row i use only rows < i."""
        rows: list[list[float]] = []
        for i, tx in enumerate(txs):
            rows.append(self.transform(tx))
            self.update(tx, bool(labels[i]) if labels is not None else False)
        return np.asarray(rows, dtype=np.float32)


def build_transaction_matrix(
    txs: list[dict], labels: list[bool] | None = None
) -> np.ndarray:
    """Convenience wrapper; `txs` must be sorted ascending by timestamp."""
    return TransactionFeatureBuilder().transform_many(txs, labels)


# ---------------------------------------------------------------------------
# Borrower / repayment features
# ---------------------------------------------------------------------------
def _trend(values: list[float]) -> float:
    if len(values) < 6:
        return 0.0
    head = float(np.mean(values[:3]))
    tail = float(np.mean(values[-3:]))
    if abs(head) < 1e-6:
        return 0.0
    return float(np.clip((tail - head) / abs(head), -3, 3))


def _volatility(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = float(np.mean(values))
    if abs(mean) < 1e-6:
        return 0.0
    return float(np.clip(float(np.std(values)) / abs(mean), 0, 5))


def build_repayment_features(
    borrower: dict,
    loans: list[dict],
    repayments: list[dict],
    now: dt.datetime | None = None,
) -> np.ndarray:
    """Build the repayment-risk feature vector for one borrower."""
    now = now or dt.datetime.now()
    loans = loans or []
    loan_ids = {ln["id"] for ln in loans}
    reps = [r for r in (repayments or []) if r["loan_id"] in loan_ids]

    income = max(float(borrower.get("monthly_income") or 0.0), 1.0)
    spending = float(borrower.get("monthly_spending") or 0.0)
    outstanding = sum(float(ln.get("outstanding_amount") or 0.0) for ln in loans)
    principal = sum(float(ln.get("principal") or 0.0) for ln in loans)
    emi = sum(float(ln.get("monthly_emi") or 0.0) for ln in loans if ln.get("status") == "active")
    active_loans = sum(1 for ln in loans if ln.get("status") == "active")

    settled = [r for r in reps if r.get("status") in {"paid", "late", "missed", "partial"}]
    paid = sum(1 for r in settled if r["status"] == "paid")
    late = sum(1 for r in settled if r["status"] == "late")
    missed = sum(1 for r in settled if r["status"] == "missed")
    partial = sum(1 for r in settled if r["status"] == "partial")
    on_time_ratio = paid / len(settled) if settled else 1.0

    delinquency_30d = 0.0
    for r in settled:
        due = r.get("due_date")
        if due and r["status"] in {"late", "missed", "partial"}:
            if (now - due).days <= 30:
                delinquency_30d = 1.0
                break

    income_history = [float(v) for v in (borrower.get("income_history") or [])]
    spending_history = [float(v) for v in (borrower.get("spending_history") or [])]

    existing_debt = float(borrower.get("total_existing_debt") or 0.0)
    utilisation = float(borrower.get("credit_utilization") or 0.0)

    if loans:
        earliest = min(ln["disbursed_at"] for ln in loans)
        months_since = max((now - earliest).days / 30.44, 0.0)
        avg_util = float(
            np.mean(
                [
                    (float(ln["principal"]) - float(ln["outstanding_amount"]))
                    / max(float(ln["principal"]), 1.0)
                    for ln in loans
                ]
            )
        )
    else:
        months_since = 0.0
        avg_util = 0.0

    vector = [
        float(np.log1p(outstanding)),
        emi,
        emi / income,
        outstanding / (income * 12.0),
        on_time_ratio,
        float(missed),
        float(late),
        float(partial),
        delinquency_30d,
        float(np.log1p(income)),
        _trend(income_history),
        _volatility(income_history),
        float(borrower.get("employment_years") or 0.0),
        1.0 if borrower.get("employment_stable") else 0.0,
        existing_debt,
        existing_debt / (income * 12.0),
        float(np.clip(utilisation, 0, 3)),
        _trend(spending_history),
        spending / income,
        float(active_loans),
        avg_util,
        months_since,
    ]
    return np.asarray(vector, dtype=np.float32)
