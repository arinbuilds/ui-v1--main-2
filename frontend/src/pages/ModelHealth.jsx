import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import api from '../api.js';
import { useApi } from '../hooks/useApi.js';
import { Card, Badge, ModelBadge, Loading, ErrorBox, Note } from '../components/ui.jsx';
import { num, titleCase, shortDate } from '../lib/format.js';

export default function ModelHealth() {
  const health = useApi(() => api.health(), []);
  const thresholds = useApi(() => api.thresholds(), []);
  const cats = useApi(() => api.scamCategories(), []);

  const loaded = health.data?.models || {};
  const kinds = useMemo(
    () => Object.entries(loaded).map(([k, m]) => ({ key: k, ...m })),
    [loaded],
  );

  return (
    <div className="stack">
      <Card title="Artifact status" subtitle="Metrics are logged by the backend at startup">
        {health.loading && <Loading />}
        {health.error && <ErrorBox error={health.error} onRetry={health.refetch} />}
        {!health.loading && !health.error && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Kind</th>
                  <th>Loaded</th>
                  <th>Model</th>
                  <th>Task</th>
                  <th>Forced fallback</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {kinds.map(({ key, loaded: ok, model_used, kind, task, forced_fallback, error }) => (
                  <tr key={key}>
                    <td className="strong">{titleCase(key)}</td>
                    <td>
                      <Badge tone={ok ? 'ok' : 'critical'}>{ok ? 'yes' : 'no'}</Badge>
                    </td>
                    <td>
                      <ModelBadge modelUsed={model_used} status={null} />
                    </td>
                    <td>{kind || '—'}</td>
                    <td>
                      {forced_fallback ? (
                        <Badge tone="critical">yes — all preds fallback</Badge>
                      ) : (
                        <Badge tone="ok">no</Badge>
                      )}
                    </td>
                    <td className="dim">{error || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title="Published thresholds (single source of truth)"
        subtitle="The UI renders these values; React never recomputes risk bands"
      >
        <div className="grid grid-2">
          <div className="grid grid-4" style={{ gap: 10 }}>
            {thresholds.data?.risk_bands?.map((b) => (
              <div key={b.label}>
                <div className="spread" style={{ justifyContent: 'space-between' }}>
                  <span className="strong">{b.label}</span>
                  <span className="faint">{b.from}–{b.to}</span>
                </div>
                <div className="hbar" style={{ marginTop: 4 }}>
                  <span
                    style={{
                      width: `calc(${(b.to - b.from) / 100 * 100}% + ${100 - b.to}%)`,
                      background: `var(--${b.level})`,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="grid grid-3" style={{ gap: 10 }}>
            <div>
              <div className="faint" style={{ fontSize: 11 }}>Fraud suspicious</div>
              <div className="mono" style={{ fontSize: 13 }}>
                {thresholds.data?.fraud_suspicious_threshold}
              </div>
            </div>
            <div>
              <div className="faint" style={{ fontSize: 11 }}>Fraud review</div>
              <div className="mono" style={{ fontSize: 13 }}>
                {thresholds.data?.fraud_review_threshold}
              </div>
            </div>
            <div>
              <div className="faint" style={{ fontSize: 11 }}>Anomaly</div>
              <div className="mono" style={{ fontSize: 13 }}>
                {thresholds.data?.anomaly_threshold}
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card title="Scam categories" subtitle="MLEXT multiclass labels from the XGBoost scam classifier">
        <div className="chip-row">
          {(cats.data?.categories || []).map((c) => (
            <Badge key={c.key} tone="neutral">
              {c.label}
            </Badge>
          ))}
        </div>
      </Card>

      <Card title="Forced fallback demo">
        <div className="grid grid-2">
          <div>
            <div className="faint" style={{ fontSize: 11 }}>
              Set {num(1)} environment variable to demo the fallback path
            </div>
            <div className="mono" style={{ fontSize: 12, marginTop: 6 }}>
              RISKGUARD_FORCE_FALLBACK=true
            </div>
          </div>
          <div className="spread">
            <div>
              <div className="faint" style={{ fontSize: 11 }}>
                Endpoints affected
              </div>
              <ul style={{ margin: 0, paddingLeft: 18 }} className="faint">
                <li>/g/transactions/{id}/risk</li>
                <li>/borrowers/{id}/repayment-risk</li>
                <li>/borrowers/{id}/shap</li>
              </ul>
            </div>
            <div className="faint" style={{ fontSize: 11.5 }}>
              Every returned analysis carries{' '}
              <code className="mono">model_used="fallback"</code> and
              <code className="mono">prediction_status="fallback"</code>. Nothing in the UI should
              treat a fallback prediction as a live model score — the Model Health card flags this
              state clearly.
            </div>
          </div>
        </div>
        <Note>
          Fallback contract: (1) the API never crashes on a missing model, (2) the failure is logged,
          (3) a deterministic rule scorer is used, and (4) the response is explicitly marked fallback.
        </Note>
      </Card>
    </div>
  );
}
