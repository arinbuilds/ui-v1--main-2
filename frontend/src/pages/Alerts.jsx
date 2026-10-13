import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api.js';
import { useApi } from '../hooks/useApi.js';
import { Card, Badge, Loading, ErrorBox, Empty, Note } from '../components/ui.jsx';
import { num, relative, titleCase } from '../lib/format.js';

const SEV_TONE = { critical: 'critical', high: 'danger', medium: 'warn', low: 'neutral' };
const STATUS_TONE = { open: 'warn', acknowledged: 'accent', resolved: 'ok' };

export default function Alerts() {
  const [kind, setKind] = useState('');
  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(null);

  const params = useMemo(
    () => ({
      kind: kind || undefined,
      severity: severity || undefined,
      status: status || undefined,
      limit: 300,
    }),
    [kind, severity, status],
  );

  const { data, loading, error, refetch } = useApi(() => api.alerts(params), [params]);

  async function setAlertStatus(id, next) {
    setBusy(id);
    try {
      await api.updateAlert(id, next);
      await refetch();
    } finally {
      setBusy(null);
    }
  }

  const items = data?.items || [];
  const counts = data?.counts || {};

  return (
    <div className="stack">
      <div className="grid grid-4">
        <Card title="Open" subtitle="Needs analyst action">
          <div className="kpi-value" style={{ color: 'var(--warn)' }}>
            {num(counts.open ?? 0)}
          </div>
        </Card>
        <Card title="Acknowledged">
          <div className="kpi-value">{num(counts.acknowledged ?? 0)}</div>
        </Card>
        <Card title="Resolved">
          <div className="kpi-value" style={{ color: 'var(--ok)' }}>
            {num(counts.resolved ?? 0)}
          </div>
        </Card>
        <Card title="Total">
          <div className="kpi-value">{num(data?.total ?? 0)}</div>
        </Card>
      </div>

      <Card
        title="Filters"
        action={
          <button className="btn ghost sm" onClick={refetch}>
            Refresh
          </button>
        }
      >
        <div className="controls">
          <select value={kind} onChange={(e) => setKind(e.target.value)}>
            <option value="">All kinds</option>
            {['fraud', 'anomaly', 'early_warning', 'scam'].map((k) => (
              <option key={k} value={k}>
                {titleCase(k)}
              </option>
            ))}
          </select>
          <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">All severities</option>
            {['critical', 'high', 'medium', 'low'].map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {['open', 'acknowledged', 'resolved'].map((s) => (
              <option key={s} value={s}>
                {titleCase(s)}
              </option>
            ))}
          </select>
        </div>
      </Card>

      {error && <ErrorBox error={error} onRetry={refetch} />}
      {loading && !items.length && <Loading />}
      {!loading && !items.length && !error && <Empty label="No alerts match these filters" />}

      {items.map((a) => (
        <Card key={a.id}>
          <div className="spread" style={{ alignItems: 'flex-start' }}>
            <div style={{ minWidth: 0 }}>
              <div className="row wrap" style={{ gap: 8 }}>
                <Badge tone={SEV_TONE[a.severity] || 'neutral'}>{a.severity}</Badge>
                <Badge tone="neutral">{titleCase(a.kind)}</Badge>
                <Badge tone={STATUS_TONE[a.status] || 'neutral'}>{a.status}</Badge>
                {a.score != null && <Badge tone="accent">score {Number(a.score).toFixed(0)}</Badge>}
              </div>
              <div className="strong" style={{ fontSize: 14, marginTop: 8 }}>
                {a.title}
              </div>
              <div className="dim" style={{ fontSize: 12.5, marginTop: 3 }}>
                {a.message}
              </div>
              {(a.reasons || []).length > 0 && (
                <ul style={{ margin: '8px 0 0', paddingLeft: 18 }} className="faint">
                  {a.reasons.map((r, i) => (
                    <li key={i} style={{ fontSize: 11.5 }}>
                      {r}
                    </li>
                  ))}
                </ul>
              )}
              <div className="faint" style={{ fontSize: 11, marginTop: 8 }}>
                {titleCase(a.subject_type)} {a.subject_type === 'transaction' ? (
                  <Link className="mono" to={`/transactions/${a.subject_id}`}>
                    {a.subject_id}
                  </Link>
                ) : (
                  <Link className="mono" to={`/borrowers/${a.subject_id}`}>
                    {a.subject_id}
                  </Link>
                )}{' '}
                · {relative(a.created_at)}
              </div>
            </div>
            <div className="row" style={{ gap: 6 }}>
              {a.status !== 'acknowledged' && (
                <button
                  className="btn ghost sm"
                  disabled={busy === a.id}
                  onClick={() => setAlertStatus(a.id, 'acknowledged')}
                >
                  Acknowledge
                </button>
              )}
              {a.status !== 'resolved' && (
                <button
                  className="btn sm"
                  disabled={busy === a.id}
                  onClick={() => setAlertStatus(a.id, 'resolved')}
                >
                  Resolve
                </button>
              )}
              {a.status === 'resolved' && (
                <button
                  className="btn ghost sm"
                  disabled={busy === a.id}
                  onClick={() => setAlertStatus(a.id, 'open')}
                >
                  Reopen
                </button>
              )}
            </div>
          </div>
        </Card>
      ))}

      {items.length > 0 && (
        <Note>
          Alerts are generated by the backend from model output (fraud score, Isolation Forest
          anomalies, scam classification and early-warning signals) — never created by the UI.
        </Note>
      )}
    </div>
  );
}
