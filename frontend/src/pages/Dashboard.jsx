import { Link } from 'react-router-dom';
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import api from '../api.js';
import { useApi } from '../hooks/useApi.js';
import {
  Card,
  Kpi,
  Badge,
  RiskBadge,
  ModelBadge,
  ScoreCell,
  Loading,
  ErrorBox,
  Empty,
  Note,
} from '../components/ui.jsx';
import { inr, num, relative, dateTime, titleCase, levelFromCategory } from '../lib/format.js';

const PIE_COLORS = ['#4f8cff', '#8a5cff', '#ff7a45', '#f0b429', '#35c88a', '#ff4d6d', '#6b7891'];

const tooltipStyle = {
  background: '#151c2c',
  border: '1px solid #243049',
  borderRadius: 8,
  fontSize: 12,
  color: '#e8edf7',
};

export default function Dashboard() {
  const { data, loading, error, refetch } = useApi(() => api.dashboard(), []);

  if (loading) return <Loading label="Aggregating dashboard…" />;
  if (error) return <ErrorBox error={error} onRetry={refetch} />;
  if (!data) return <Empty />;

  const k = data.kpis || {};
  const ms = data.model_status || {};
  const fallbackInUse = Object.values(ms).some((m) => m && (m.forced_fallback || !m.loaded));

  return (
    <div className="stack">
      {/* ------------------------------------------------------------ KPIs */}
      <div className="grid grid-kpi">
        <Kpi
          label="Transactions"
          value={num(k.transactions_total)}
          foot={`Volume ${inr(k.transaction_volume, { compact: true })}`}
        />
        <Kpi
          label="Suspicious"
          value={num(k.suspicious_transactions)}
          foot={`${num(k.review_transactions)} flagged for review`}
          tone="critical"
        />
        <Kpi
          label="Anomalies (Isolation Forest)"
          value={num(k.anomalies_detected)}
          foot={`${num(k.anomalies_not_fraud)} not high-risk fraud score`}
          tone="warn"
        />
        <Kpi
          label="Avg Fraud Score"
          value={`${k.fraud_score_avg ?? '—'}/100`}
          foot="Across all scored transactions"
        />
        <Kpi
          label="Borrowers"
          value={num(k.borrowers_total)}
          foot={`Avg repayment score ${k.repayment_score_avg ?? '—'}/100`}
        />
        <Kpi
          label="High-risk Borrowers"
          value={num(k.high_risk_borrowers)}
          foot={`${num(k.critical_borrowers)} in Critical band`}
          tone="danger"
        />
        <Kpi label="Open Alerts" value={num(k.open_alerts)} foot="Awaiting analyst action" tone="warn" />
        <Kpi
          label="Pending Interventions"
          value={num(k.pending_interventions)}
          foot={`${num(k.fallback_predictions)} fallback predictions`}
        />
      </div>

      {fallbackInUse && (
        <div className="error-box" style={{ textAlign: 'left' }}>
          ⚠ At least one model is serving the <strong>rule-based fallback</strong>. Predictions are
          still explained, but their <span className="mono">model_used</span> is{' '}
          <span className="mono">fallback</span>. See <Link to="/models">Model Health</Link>.
        </div>
      )}

      {/* -------------------------------------------------------- trends */}
      <div className="grid grid-2">
        <Card
          title="Weekly transaction volume & fraud score"
          subtitle="Aggregated by the backend from stored analysis columns"
        >
          <ResponsiveContainer width="100%" height={250}>
            <AreaChart data={data.trends || []}>
              <defs>
                <linearGradient id="amt" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4f8cff" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#4f8cff" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="sc" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ff4d6d" stopOpacity={0.5} />
                  <stop offset="100%" stopColor="#ff4d6d" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="#1c2638" vertical={false} />
              <XAxis dataKey="week" tick={{ fill: '#6b7891', fontSize: 10 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis yAxisId="l" tick={{ fill: '#6b7891', fontSize: 10 }} tickFormatter={(v) => `${(v / 1e6).toFixed(0)}M`} />
              <YAxis yAxisId="r" orientation="right" tick={{ fill: '#6b7891', fontSize: 10 }} domain={[0, 100]} />
              <Tooltip
                contentStyle={tooltipStyle}
                formatter={(v, n) => (n === 'amount' ? [inr(v, { compact: true }), 'Volume'] : [v, 'Avg score'])}
              />
              <Area yAxisId="l" type="monotone" dataKey="amount" stroke="#4f8cff" fill="url(#amt)" strokeWidth={2} />
              <Area yAxisId="r" type="monotone" dataKey="avg_fraud_score" stroke="#ff4d6d" fill="url(#sc)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Fraud score distribution" subtitle="Transactions bucketed by 0–100 risk score">
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={data.score_histogram || []}>
              <CartesianGrid stroke="#1c2638" vertical={false} />
              <XAxis dataKey="bucket" tick={{ fill: '#6b7891', fontSize: 10 }} />
              <YAxis tick={{ fill: '#6b7891', fontSize: 10 }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="count" fill="#4f8cff" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Card>
      </div>

      {/* ------------------------------------------------- scam + channels */}
      <div className="grid-3">
        <Card title="Predicted scam categories" subtitle="XGBoost multiclass over suspicious transactions">
          {(data.scam_distribution || []).length === 0 ? (
            <Empty label="No suspicious transactions classified" />
          ) : (
            <ResponsiveContainer width="100%" height={230}>
              <PieChart>
                <Pie
                  data={data.scam_distribution}
                  dataKey="count"
                  nameKey="label"
                  innerRadius={48}
                  outerRadius={82}
                  paddingAngle={2}
                >
                  {data.scam_distribution.map((_, i) => (
                    <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip contentStyle={tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
          )}
          <div className="legend" style={{ marginTop: 10 }}>
            {(data.scam_distribution || []).map((s, i) => (
              <span key={s.key}>
                <i style={{ background: PIE_COLORS[i % PIE_COLORS.length] }} />
                {s.label} · {s.count}
              </span>
            ))}
          </div>
        </Card>

        <Card title="Channel risk profile" subtitle="Average fraud score by payment channel">
          <table className="data">
            <thead>
              <tr>
                <th>Channel</th>
                <th className="right">Txns</th>
                <th className="right">Avg score</th>
                <th className="right">Suspicious</th>
              </tr>
            </thead>
            <tbody>
              {(data.channels || []).map((c) => (
                <tr key={c.channel}>
                  <td className="strong">{titleCase(c.channel)}</td>
                  <td className="right">{num(c.count)}</td>
                  <td className="right">
                    {/* fixed 0–100 scale from the API contract — not a risk-band re-derivation */}
                    <div className="score-cell">
                      <span className="score-num">{Number(c.avg_score).toFixed(0)}</span>
                      <div style={{ flex: 1, minWidth: 60 }}>
                        <div className="score-bar">
                          <span className="fill-neutral" style={{ width: `${c.avg_score}%` }} />
                        </div>
                      </div>
                    </div>
                  </td>
                  <td className="right">{num(c.suspicious)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card title="Repayment risk mix" subtitle="Borrowers by XGBoost repayment band">
          {(data.repayment_categories || []).map((r) => (
            <div key={r.category} style={{ marginBottom: 12 }}>
              <div className="spread" style={{ marginBottom: 5 }}>
                <span className="strong">{r.category}</span>
                <span className="dim">{r.count}</span>
              </div>
              <div className="hbar">
                <span
                  style={{
                    width: `${
                      (r.count /
                        Math.max(
                          ...(data.repayment_categories || []).map((x) => x.count),
                          1,
                        )) *
                      100
                    }%`,
                    background: `var(--${
                      { critical: 'critical', high: 'danger', moderate: 'warn', low: 'ok' }[
                        levelFromCategory(r.category)
                      ] || 'neutral'
                    })`,
                  }}
                />
              </div>
            </div>
          ))}
          <Note>
            Fraud score and repayment score are produced by independent XGBoost models and are never
            combined.
          </Note>
        </Card>
      </div>

      {/* ---------------------------------------------- suspicious + alerts */}
      <div className="grid-2">
        <Card
          title="Most suspicious transactions"
          action={
            <Link className="btn ghost sm" to="/transactions">
              View all
            </Link>
          }
        >
          {(data.recent_suspicious || []).length === 0 ? (
            <Empty label="No suspicious transactions" />
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Transaction</th>
                    <th>Amount</th>
                    <th>Score</th>
                    <th>Signals</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_suspicious.map((t) => (
                    <tr key={t.id}>
                      <td>
                        <Link to={`/transactions/${t.id}`} className="mono strong">
                          {t.id}
                        </Link>
                        <div className="faint" style={{ fontSize: 11 }}>
                          {t.sender} → {t.receiver}
                        </div>
                      </td>
                      <td className="nowrap">{inr(t.amount, { compact: true })}</td>
                      <td>
                        <div className="score-cell">
                          <span className="score-num">{t.score?.toFixed(0)}</span>
                          <RiskBadge category={t.risk_category} level={levelFromCategory(t.risk_category)} />
                        </div>
                      </td>
                      <td>
                        <div className="chip-row">
                          {t.anomaly && <Badge tone="warn">Anomaly</Badge>}
                          {t.scam_category && t.scam_category !== 'none' && (
                            <Badge tone="neutral">{titleCase(t.scam_category)}</Badge>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card
          title="Recent alerts"
          action={
            <Link className="btn ghost sm" to="/alerts">
              Alert queue
            </Link>
          }
        >
          {(data.recent_alerts || []).length === 0 ? (
            <Empty label="No alerts" />
          ) : (
            data.recent_alerts.map((a) => (
              <div className="list-item" key={a.id}>
                <Badge
                  tone={
                    a.severity === 'critical'
                      ? 'critical'
                      : a.severity === 'high'
                        ? 'danger'
                        : a.severity === 'medium'
                          ? 'warn'
                          : 'neutral'
                  }
                >
                  {a.severity}
                </Badge>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="strong" style={{ fontSize: 13 }}>
                    {a.title}
                  </div>
                  <div className="faint" style={{ fontSize: 11 }}>
                    {titleCase(a.kind)} · {a.subject_id} · {relative(a.created_at)}
                  </div>
                </div>
                <Badge tone={a.status === 'open' ? 'warn' : 'neutral'}>{a.status}</Badge>
              </div>
            ))
          )}
        </Card>
      </div>

      {/* --------------------------------------------------- top borrowers */}
      <Card
        title="Borrowers with highest repayment risk"
        subtitle="Independent XGBoost repayment model — not the fraud model"
        action={
          <Link className="btn ghost sm" to="/borrowers">
            All borrowers
          </Link>
        }
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Borrower</th>
                <th>Repayment score</th>
                <th>Band</th>
                <th>Model</th>
              </tr>
            </thead>
            <tbody>
              {(data.top_borrowers || []).map((b) => (
                <tr key={b.id} className="clickable">
                  <td>
                    <Link to={`/borrowers/${b.id}`} className="strong">
                      {b.name}
                    </Link>
                    <div className="faint mono" style={{ fontSize: 11 }}>
                      {b.id}
                    </div>
                  </td>
                  <td>
                    <ScoreCell value={b.score} level={levelFromCategory(b.category)} />
                  </td>
                  <td>
                    <RiskBadge category={b.category} level={levelFromCategory(b.category)} />
                  </td>
                  <td>
                    <ModelBadge modelUsed={b.model_used} status={b.prediction_status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <Note>
          Risk bands: {data.risk_bands?.map((b) => `${b.from}–${b.to} ${b.label}`).join(' · ')}
        </Note>
        <span className="faint" style={{ fontSize: 11 }}>
          Generated {dateTime(data.generated_at)}
        </span>
      </div>
    </div>
  );
}
