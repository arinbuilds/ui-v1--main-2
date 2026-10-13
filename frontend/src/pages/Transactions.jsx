import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api.js';
import { useApi } from '../hooks/useApi.js';
import {
  Card,
  Badge,
  RiskBadge,
  ModelBadge,
  ScoreCell,
  Loading,
  ErrorBox,
  Empty,
  Note,
} from '../components/ui.jsx';
import { inr, num, dateTime, titleCase, levelFromCategory } from '../lib/format.js';

const PAGE = 25;

export default function Transactions() {
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [channel, setChannel] = useState('');
  const [riskCategory, setRiskCategory] = useState('');
  const [decision, setDecision] = useState('');
  const [scamCategory, setScamCategory] = useState('');
  const [anomaly, setAnomaly] = useState('');
  const [modelUsed, setModelUsed] = useState('');
  const [minScore, setMinScore] = useState('');
  const [sort, setSort] = useState('score');
  const [offset, setOffset] = useState(0);

  // Categories/labels come from the backend so React never redefines them.
  const thresholds = useApi(() => api.thresholds(), []);
  const scamCats = useApi(() => api.scamCategories(), []);

  const params = useMemo(
    () => ({
      q: search || undefined,
      channel: channel || undefined,
      risk_category: riskCategory || undefined,
      decision: decision || undefined,
      scam_category: scamCategory || undefined,
      anomaly: anomaly === '' ? undefined : anomaly,
      model_used: modelUsed || undefined,
      min_score: minScore === '' ? undefined : minScore,
      sort,
      limit: PAGE,
      offset,
    }),
    [search, channel, riskCategory, decision, scamCategory, anomaly, modelUsed, minScore, sort, offset],
  );

  const { data, loading, error, refetch } = useApi(
    () => api.transactions(params),
    [params],
  );

  useEffect(() => {
    setOffset(0);
  }, [search, channel, riskCategory, decision, scamCategory, anomaly, modelUsed, minScore, sort]);

  const items = data?.items || [];
  const total = data?.total ?? 0;
  const page = Math.floor(offset / PAGE) + 1;
  const pages = Math.max(1, Math.ceil(total / PAGE));

  return (
    <div className="stack">
      <Card
        title="Filters"
        subtitle="Every filter is applied server-side; risk categories come from the backend bands"
        action={
          <button className="btn ghost sm" onClick={refetch}>
            Refresh
          </button>
        }
      >
        <div className="controls">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setSearch(q.trim());
            }}
            className="row"
            style={{ gap: 6 }}
          >
            <input
              placeholder="Search id, narrative, merchant, account, city"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ width: 290 }}
            />
            <button className="btn sm" type="submit">
              Search
            </button>
            {search && (
              <button
                className="btn ghost sm"
                type="button"
                onClick={() => {
                  setQ('');
                  setSearch('');
                }}
              >
                Clear
              </button>
            )}
          </form>

          <select value={riskCategory} onChange={(e) => setRiskCategory(e.target.value)}>
            <option value="">All risk bands</option>
            {(thresholds.data?.risk_bands || []).map((b) => (
              <option key={b.label} value={b.label}>
                {b.label} ({b.from}–{b.to})
              </option>
            ))}
          </select>

          <select value={decision} onChange={(e) => setDecision(e.target.value)}>
            <option value="">All decisions</option>
            {Object.entries(thresholds.data?.decisions || {}).map(([k, v]) => (
              <option key={k} value={v}>
                {titleCase(v)}
              </option>
            ))}
          </select>

          <select value={scamCategory} onChange={(e) => setScamCategory(e.target.value)}>
            <option value="">All scam classes</option>
            {(scamCats.data?.categories || []).map((c) => (
              <option key={c.key} value={c.key}>
                {c.label}
              </option>
            ))}
          </select>

          <select value={channel} onChange={(e) => setChannel(e.target.value)}>
            <option value="">All channels</option>
            {['upi', 'wallet', 'card', 'netbanking'].map((c) => (
              <option key={c} value={c}>
                {titleCase(c)}
              </option>
            ))}
          </select>

          <select value={anomaly} onChange={(e) => setAnomaly(e.target.value)}>
            <option value="">Anomaly: any</option>
            <option value="true">Anomalies only</option>
            <option value="false">Exclude anomalies</option>
          </select>

          <select value={modelUsed} onChange={(e) => setModelUsed(e.target.value)}>
            <option value="">Model: any</option>
            <option value="xgboost">XGBoost</option>
            <option value="fallback">Fallback</option>
          </select>

          <input
            type="number"
            min="0"
            max="100"
            placeholder="Min score"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            style={{ width: 110 }}
          />

          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="score">Sort: risk score</option>
            <option value="time">Sort: newest</option>
            <option value="amount">Sort: amount</option>
          </select>
        </div>

        <Note>
          A low fraud score is not a certificate of legitimacy — it means little fraud evidence was
          found in the available features. Isolation Forest anomalies are reported separately and are
          not automatically fraud.
        </Note>
      </Card>

      <Card
        title={`${num(total)} transactions`}
        subtitle={loading ? 'Loading…' : `Page ${page} of ${pages}`}
        action={
          <div className="row" style={{ gap: 6 }}>
            <button
              className="btn ghost sm"
              disabled={offset === 0}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
            >
              ‹ Prev
            </button>
            <button
              className="btn ghost sm"
              disabled={offset + PAGE >= total}
              onClick={() => setOffset((o) => o + PAGE)}
            >
              Next ›
            </button>
          </div>
        }
      >
        {error && <ErrorBox error={error} onRetry={refetch} />}
        {loading && !items.length && <Loading />}
        {!loading && !error && !items.length && <Empty label="No transactions match these filters" />}

        {items.length > 0 && (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Transaction</th>
                  <th>Time</th>
                  <th className="right">Amount</th>
                  <th>Channel</th>
                  <th>Risk score</th>
                  <th>Decision</th>
                  <th>Signals</th>
                  <th>Model</th>
                </tr>
              </thead>
              <tbody>
                {items.map((t) => (
                  <tr key={t.id} className="clickable">
                    <td>
                      <Link to={`/transactions/${t.id}`} className="mono strong">
                        {t.id}
                      </Link>
                      <div className="faint" style={{ fontSize: 11, maxWidth: 260 }}>
                        {t.sender?.name} → {t.receiver?.name}
                      </div>
                    </td>
                    <td className="nowrap dim" style={{ fontSize: 12 }}>
                      {dateTime(t.ts)}
                    </td>
                    <td className="right nowrap">{inr(t.amount, { compact: true })}</td>
                    <td>
                      <Badge tone="neutral">{titleCase(t.channel)}</Badge>
                    </td>
                    <td style={{ minWidth: 150 }}>
                      <ScoreCell value={t.fraud_score} level={levelFromCategory(t.risk_category)} />
                      <div style={{ marginTop: 4 }}>
                        <RiskBadge category={t.risk_category} level={levelFromCategory(t.risk_category)} />
                      </div>
                    </td>
                    <td>
                      <Badge
                        tone={
                          t.decision === 'suspicious'
                            ? 'critical'
                            : t.decision === 'review_recommended'
                              ? 'warn'
                              : 'ok'
                        }
                      >
                        {titleCase(t.decision)}
                      </Badge>
                    </td>
                    <td>
                      <div className="chip-row">
                        {t.anomaly?.is_anomaly && (
                          <Badge tone="warn" dot>
                            Anomaly {t.anomaly.anomaly_score?.toFixed(0)}
                          </Badge>
                        )}
                        {t.scam?.scam_category && t.scam.scam_category !== 'none' && (
                          <Badge tone="accent">{t.scam.label || titleCase(t.scam.scam_category)}</Badge>
                        )}
                        {t.counterparty_is_new && <Badge tone="neutral">New counterparty</Badge>}
                      </div>
                    </td>
                    <td>
                      <ModelBadge modelUsed={t.model_used} status={t.prediction_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}