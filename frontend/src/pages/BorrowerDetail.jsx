import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  Cell,
  ReferenceLine,
} from 'recharts';
import api from '../api.js';
import { useApi } from '../hooks/useApi.js';
import {
  Card,
  Badge,
  RiskBadge,
  ModelBadge,
  ScoreBar,
  Loading,
  ErrorBox,
  Empty,
  FactorList,
  Explain,
  Note,
  StatMini,
} from '../components/ui.jsx';
import { inr, dateTime, shortDate, titleCase, levelFromCategory, toneForLevel, pct } from '../lib/format.js';

const SEV_TONE = { critical: 'critical', high: 'danger', medium: 'warn', low: 'neutral' };

const tooltipStyle = {
  background: '#151c2c',
  border: '1px solid #243049',
  borderRadius: 8,
  fontSize: 12,
  color: '#e8edf7',
};

export default function BorrowerDetail() {
  const { id } = useParams();
  const detail = useApi(() => api.borrower(id), [id]);
  const shap = useApi(() => api.borrowerShap(id), [id]);
  const warnings = useApi(() => api.earlyWarnings(id), [id]);
  const timeline = useApi(() => api.borrowerTimeline(id, { limit: 120 }), [id]);
  const [loanId, setLoanId] = useState(null);
  const [live, setLive] = useState(null);
  const [rescoring, setRescoring] = useState(false);

  const b = detail.data;
  const rep = live || b?.repayment;
  const level = levelFromCategory(rep?.risk_category);
  const tone = toneForLevel(level);

  async function rescore() {
    setRescoring(true);
    try {
      setLive(await api.repaymentRisk(id));
    } catch {
      /* handled by useApi error surfaces elsewhere */
    } finally {
      setRescoring(false);
    }
  }

  if (detail.loading) return <Loading label="Loading borrower…" />;
  if (detail.error) return <ErrorBox error={detail.error} onRetry={detail.refetch} />;
  if (!b) return <Empty label="Borrower not found" />;

  const activeLoan = loanId || b.loans?.[0]?.id;
  const shapChart = (shap.data?.chart || []).map((c) => ({
    ...c,
    label: c.label || c.feature,
  }));

  return (
    <div className="stack">
      <div className="row wrap" style={{ gap: 10 }}>
        <Link className="btn ghost sm" to="/borrowers">
          ‹ Back to borrowers
        </Link>
        <div style={{ flex: 1 }} />
        <button className="btn sm" onClick={rescore} disabled={rescoring}>
          {rescoring ? 'Scoring…' : 'Re-score live (ML layer)'}
        </button>
      </div>

      {/* --------------------------------------------------------- profile */}
      <div className="grid grid-3">
        <Card title={b.name} subtitle={`${b.id} · ${b.account?.bank || '—'}`}>
          <div className="grid grid-2" style={{ gap: 10 }}>
            <StatMini value={b.occupation || '—'} label="Occupation" />
            <StatMini value={b.employer || '—'} label="Employer" />
            <StatMini value={b.city || '—'} label="City" />
            <StatMini value={`${b.employment_years ?? '—'} yrs`} label="Employment" />
            <StatMini value={inr(b.monthly_income, { compact: true })} label="Monthly income" />
            <StatMini value={inr(b.monthly_spending, { compact: true })} label="Monthly spending" />
          </div>
          <div className="divider" />
          <div className="row wrap" style={{ gap: 6 }}>
            <Badge tone={b.employment_stable ? 'ok' : 'warn'}>
              {b.employment_stable ? 'Stable employment' : 'Unstable employment'}
            </Badge>
            <Badge tone="neutral">Credit utilisation {pct(b.credit_utilization)}</Badge>
            <Badge tone="neutral">Existing debt {inr(b.total_existing_debt, { compact: true })}</Badge>
          </div>
        </Card>

        <Card title="Repayment risk" subtitle="XGBoost repayment model (independent of fraud)">
          <div className="row" style={{ alignItems: 'flex-end', gap: 12 }}>
            <div className="kpi-value" style={{ color: `var(--${tone})` }}>
              {Number(rep?.score ?? 0).toFixed(0)}
            </div>
            <div style={{ paddingBottom: 4 }}>
              <RiskBadge category={rep?.risk_category} level={level} />
            </div>
          </div>
          <div style={{ margin: '10px 0' }}>
            <ScoreBar value={rep?.score} level={level} />
          </div>
          <div className="row wrap" style={{ gap: 6 }}>
            <ModelBadge modelUsed={rep?.model_used} status={rep?.prediction_status} />
            {rep?.confidence != null && (
              <Badge tone="neutral">confidence {(rep.confidence * 100).toFixed(1)}%</Badge>
            )}
          </div>
          {rep?.explanation && (
            <div style={{ marginTop: 10 }}>
              <Note>{rep.explanation}</Note>
            </div>
          )}
          <div className="divider" />
          <div className="grid grid-2" style={{ gap: 10 }}>
            <StatMini value={inr(b.total_outstanding, { compact: true })} label="Total outstanding" />
            <StatMini value={inr(b.monthly_emi_total, { compact: true })} label="Monthly EMI" />
            <StatMini value={b.loans?.length ?? 0} label="Loans" />
            <StatMini value={inr(b.total_principal, { compact: true })} label="Total principal" />
          </div>
        </Card>

        <Card
          title="Early warning"
          subtitle={warnings.data?.level ? `Level: ${titleCase(warnings.data.level)}` : 'Leading indicators'}
        >
          {warnings.loading && <Loading label="Evaluating signals…" />}
          {warnings.error && <ErrorBox error={warnings.error} onRetry={warnings.refetch} />}
          {warnings.data?.summary && <Explain>{warnings.data.summary}</Explain>}
          <div style={{ marginTop: 12 }}>
            {(warnings.data?.signals || []).map((s) => (
              <div className="list-item" key={s.code}>
                <Badge tone={SEV_TONE[s.severity] || 'neutral'}>{s.severity}</Badge>
                <div>
                  <div className="strong" style={{ fontSize: 13 }}>
                    {s.label}
                  </div>
                  <div className="faint" style={{ fontSize: 11.5 }}>
                    {s.message}
                  </div>
                </div>
              </div>
            ))}
            {!warnings.loading && !(warnings.data?.signals || []).length && (
              <Empty label="No early-warning indicators" />
            )}
          </div>
          <Note>{warnings.data?.note}</Note>
        </Card>
      </div>

      {/* ------------------------------------------------------ SHAP chart */}
      <Card
        title="SHAP explanation — repayment risk"
        subtitle="Computed by the ML layer with shap.TreeExplainer; positive pushes risk up, negative down"
      >
        {shap.loading && <Loading label="Computing SHAP values…" />}
        {shap.error && <ErrorBox error={shap.error} onRetry={shap.refetch} />}
        {shapChart.length > 0 && (
          <>
            <ResponsiveContainer width="100%" height={Math.max(220, shapChart.length * 30)}>
              <BarChart data={shapChart} layout="vertical" margin={{ left: 30, right: 30 }}>
                <CartesianGrid stroke="#1c2638" horizontal={false} />
                <XAxis type="number" tick={{ fill: '#6b7891', fontSize: 10 }} />
                <YAxis
                  type="category"
                  dataKey="label"
                  width={180}
                  tick={{ fill: '#97a3bb', fontSize: 11 }}
                />
                <Tooltip contentStyle={tooltipStyle} />
                <ReferenceLine x={0} stroke="#3a4a68" />
                <Bar dataKey="contribution" radius={[3, 3, 3, 3]}>
                  {shapChart.map((c, i) => (
                    <Cell key={i} fill={c.contribution >= 0 ? '#ff4d6d' : '#35c88a'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
            <div className="divider" />
          </>
        )}
        {shap.data?.summary && <Explain>{shap.data.summary}</Explain>}
        <div style={{ marginTop: 12 }}>
          <FactorList factors={shap.data?.contributions || []} />
        </div>
        <Note>
          Base value {shap.data?.base_value?.toFixed?.(3) ?? '—'} · model {shap.data?.model_used} ·
          status {shap.data?.prediction_status}. SHAP values are produced in the Python ML layer and
          rendered here as-is.
        </Note>
      </Card>

      {/* ------------------------------------------------- loans + timeline */}
      <div className="grid-2">
        <Card
          title="Loans"
          subtitle="Select a loan to inspect its transaction-level usage"
          action={
            <select value={activeLoan || ''} onChange={(e) => setLoanId(e.target.value)}>
              {(b.loans || []).map((l) => (
                <option key={l.id} value={l.id}>
                  {l.id} — {l.purpose}
                </option>
              ))}
            </select>
          }
        >
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Loan</th>
                  <th className="right">Principal</th>
                  <th className="right">Outstanding</th>
                  <th className="right">EMI</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {(b.loans || []).map((l) => (
                  <tr key={l.id}>
                    <td>
                      <div className="strong">{l.id}</div>
                      <div className="faint" style={{ fontSize: 11 }}>
                        {l.purpose} · {l.term_months}m · {l.interest_rate}%
                      </div>
                    </td>
                    <td className="right nowrap">{inr(l.principal, { compact: true })}</td>
                    <td className="right nowrap">{inr(l.outstanding_amount, { compact: true })}</td>
                    <td className="right nowrap">{inr(l.monthly_emi, { compact: true })}</td>
                    <td>
                      <Badge tone={l.status === 'active' ? 'accent' : 'neutral'}>{l.status}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <LoanUsage loanId={activeLoan} />
      </div>

      <Card title="Activity timeline" subtitle="Loans, repayments and transactions around this borrower">
        {timeline.loading && <Loading />}
        {timeline.error && <ErrorBox error={timeline.error} onRetry={timeline.refetch} />}
        <div className="scroll-360">
          <div className="timeline">
            {(timeline.data?.events || []).map((e, i) => (
              <div className={`timeline-item ${e.type}`} key={`${e.type}-${i}`}>
                <div className="spread">
                  <div>
                    <div className="strong" style={{ fontSize: 13 }}>
                      {e.title}
                    </div>
                    <div className="faint" style={{ fontSize: 11 }}>
                      {dateTime(e.ts)}
                      {e.meta ? ` · ${e.meta}` : ''}
                    </div>
                  </div>
                  <div className="row" style={{ gap: 6 }}>
                    {e.amount != null && <span className="nowrap">{inr(e.amount, { compact: true })}</span>}
                    {e.type === 'transaction' && e.risk_category && (
                      <RiskBadge category={e.risk_category} level={levelFromCategory(e.risk_category)} />
                    )}
                    {e.is_anomaly && <Badge tone="warn">Anomaly</Badge>}
                    {e.type === 'repayment' && (
                      <Badge tone={e.status === 'paid' ? 'ok' : e.status === 'upcoming' ? 'neutral' : 'warn'}>
                        {e.status}
                      </Badge>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
        {(timeline.data?.spend_breakdown || []).length > 0 && (
          <>
            <div className="divider" />
            <div className="strong" style={{ fontSize: 13, marginBottom: 8 }}>
              Spending around loan events
            </div>
            {timeline.data.spend_breakdown.map((s) => (
              <div key={s.category} style={{ marginBottom: 8 }}>
                <div className="spread" style={{ fontSize: 12 }}>
                  <span>{s.category}</span>
                  <span className="dim">
                    {inr(s.amount, { compact: true })} · {s.count} txns
                  </span>
                </div>
                <div className="hbar" style={{ marginTop: 4 }}>
                  <span
                    style={{
                      width: `${
                        (s.amount /
                          Math.max(...timeline.data.spend_breakdown.map((x) => x.amount), 1)) *
                        100
                      }%`,
                    }}
                  />
                </div>
              </div>
            ))}
            <Note>{timeline.data.spend_note}</Note>
          </>
        )}
      </Card>
    </div>
  );
}

function LoanUsage({ loanId }) {
  const { data, loading, error, refetch } = useApi(
    () => api.loanUsage(loanId),
    [loanId],
    { immediate: Boolean(loanId) },
  );

  if (!loanId) return <Card title="Loan usage"><Empty label="No loan selected" /></Card>;
  if (loading) return <Card title="Loan usage"><Loading /></Card>;
  if (error) return <Card title="Loan usage"><ErrorBox error={error} onRetry={refetch} /></Card>;
  if (!data) return <Card title="Loan usage"><Empty /></Card>;

  return (
    <Card
      title={`Loan usage — ${data.loan_id}`}
      subtitle={`Intended use: ${data.intended_use || '—'} · disbursed ${shortDate(data.disbursed_at)}`}
    >
      <div className="grid grid-3" style={{ gap: 10 }}>
        <StatMini value={inr(data.flow?.disbursed_amount, { compact: true })} label="Disbursed" />
        <StatMini value={inr(data.flow?.spent_amount, { compact: true })} label="Spent" />
        <StatMini value={inr(data.flow?.repaid_amount, { compact: true })} label="Repaid" />
      </div>
      <div className="divider" />
      {(data.spend_breakdown || []).map((s) => (
        <div key={s.category} style={{ marginBottom: 9 }}>
          <div className="spread" style={{ fontSize: 12 }}>
            <span>{s.category}</span>
            <span className="dim">
              {inr(s.amount, { compact: true })} · {(s.share * 100).toFixed(0)}%
            </span>
          </div>
          <div className="hbar" style={{ marginTop: 4 }}>
            <span style={{ width: `${s.share * 100}%` }} />
          </div>
        </div>
      ))}
      <Note>{data.note}</Note>
    </Card>
  );
}
