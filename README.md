# FraudShield — AI Financial Scam Detection & Loan Risk Management (Prototype)

Synthetic-data risk intelligence platform. Hybrid **rules + ML + behavioural + anomaly + clustering**.
Clearly labeled **Prototype / Synthetic Data / Potential Scam / Requires Review**. Freezes are **simulated**.

## Architecture

- `frontend/` — Next.js 16 + TypeScript + Tailwind v4 + Recharts + Framer Motion + Lucide. Routes: `/`, `/transactions`, `/alerts`, `/customers`, `/customer/[id]`, `/scams`, `/emerging`, `/loans`, `/loans/[id]`, `/cases`, `/cases/[id]`, `/analytics`, `/data`, `/settings`.
- `backend/` — FastAPI (`main:app`). Modules: `synthetic.py` (seed-42 generator), `behaviour.py` (personal baseline), `ml.py` (RandomForest + IsolationForest + DBSCAN pipelines), `risk.py` (separate fraud/repayment scores), `store.py` (scores, alerts, cases, patterns).
- `supabase/schema.sql` — PostgreSQL schema. Seed via `backend/data/seed.json` (auto-generated on backend startup).
- `backend/data/seed.json` — generated fallback dataset (also used if API offline).

## Run

Backend (port 8000):
```
cd backend
pip install -r requirements.txt
fastapi dev main.py
```

Frontend:
```
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000. Backend health: http://localhost:8000/api/health.

## Demo flow (judges)

1. `/data` → **Load demo: Emerging Scam Cluster** (or Payment Request / Mule / High Repayment / Normal).
2. Customer page shows **Fraud vs Repayment scores kept separate** (e.g. Ravi Kulkarni Fraud 99 / Repayment 8).
3. Transaction panel → behavioural deviations + live ML category + confidence (real `/api/ml/predict`, not faked).
4. `/alerts` → WHY explanation with point contributions + clickable evidence.
5. `/emerging` → PAT cluster graph → Confirm / Investigate / False Positive (confirmed → eligible for training).
6. `/cases` → investigate → simulated freeze → resolve; timeline + notes + follow-ups.
7. `/loans` → outstanding, delayed/missed, repayment timeline, purpose-context signal.

## Notes

- Train accuracy 1.0 on synthetic seed (expected — deterministic scenarios); predictions served live from sklearn pipeline.
- Phishing/impersonation use synthetic contextual metadata; UI never claims transaction data alone proves them.
- Deploy: Vercel (frontend), Render/Railway `fastapi run` (backend), Supabase (schema.sql).
