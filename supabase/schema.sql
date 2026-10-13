-- FraudShield Supabase PostgreSQL schema (synthetic demo data)
create table if not exists customers (
  customer_id text primary key, name text not null, age int, location text,
  occupation text, job_history jsonb default '[]', monthly_income numeric,
  income_trend jsonb default '[]', credit_score int, total_assets numeric,
  total_debt numeric, account_age_months int, normal_min numeric, normal_max numeric,
  normal_freq_per_day numeric, risk_profile text, fraud_score int default 0,
  repayment_score int default 0, fraud_level text default 'LOW', repayment_level text default 'LOW'
);
create table if not exists behaviour_profiles (
  customer_id text primary key references customers(customer_id),
  average_transaction_amount numeric, average_daily_transactions numeric,
  common_locations jsonb default '[]', common_merchants jsonb default '[]',
  common_beneficiaries jsonb default '[]', normal_hours_start int default 10,
  normal_hours_end int default 21, normal_channels jsonb default '["UPI","Card"]'
);
create table if not exists transactions (
  transaction_id text primary key, customer_id text references customers(customer_id),
  timestamp timestamptz, amount numeric, transaction_type text, payment_channel text,
  merchant text, beneficiary text, location text, device_id text,
  expected_purpose text, actual_purpose text, expected_relation text, beneficiary_relation text,
  transaction_status text default 'completed', scam_label boolean default false,
  scam_category text default 'Legitimate', anomaly_score numeric default 0, fraud_risk int default 0,
  is_new_beneficiary boolean default false, is_new_device boolean default false,
  is_unusual_time boolean default false, is_unusual_location boolean default false,
  amount_multiple numeric default 1
);
create index if not exists idx_txn_customer on transactions(customer_id);
create index if not exists idx_txn_time on transactions(timestamp desc);
create index if not exists idx_txn_risk on transactions(fraud_risk desc);
create table if not exists loans (
  loan_id text primary key, customer_id text references customers(customer_id),
  loan_type text, loan_amount numeric, outstanding_balance numeric, interest_rate numeric,
  start_date date, due_date date, monthly_payment numeric, loan_purpose text, status text
);
create table if not exists repayments (
  repayment_id text primary key, loan_id text references loans(loan_id),
  customer_id text references customers(customer_id), due_date date, payment_date date,
  amount_due numeric, amount_paid numeric, status text, days_delayed int default 0
);
create index if not exists idx_rep_loan on repayments(loan_id);
create table if not exists reports (
  report_id text primary key, customer_id text references customers(customer_id),
  transaction_id text, report_type text, description text, severity text,
  created_at timestamptz, status text
);
create table if not exists risk_alerts (
  alert_id text primary key, customer_id text references customers(customer_id),
  transaction_id text, risk_type text, score int, severity text, title text,
  explanation text, evidence jsonb default '[]', breakdown jsonb default '[]',
  status text default 'OPEN', created_at timestamptz
);
create index if not exists idx_alert_customer on risk_alerts(customer_id);
create table if not exists interventions (
  intervention_id text primary key, alert_id text, customer_id text references customers(customer_id),
  intervention_type text, status text default 'OPEN', priority text default 'MEDIUM',
  assigned_to text, notes text, due_date date, frozen_simulated boolean default false,
  timeline jsonb default '[]', created_at timestamptz, updated_at timestamptz
);
create table if not exists emerging_patterns (
  pattern_id text primary key, detected_at timestamptz, affected_customers jsonb default '[]',
  affected_transactions jsonb default '[]', common_features jsonb default '[]',
  confidence numeric, status text default 'POTENTIAL', analyst_verdict text, description text
);
-- Seed via backend: python -c "from app import store; store.load()" then import backend/data/seed.json
