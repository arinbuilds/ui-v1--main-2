import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
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
import { inr, dateTime, titleCase, levelFromCategory, toneForLevel } from '../lib/format.js';

export default function TransactionDetail() {
  const { id } = useParams();
  const tx = useApi(() => api.transaction(id), [id]);
  const [live, setLive] = useState(null);
  const [rescoring, setRescoring] = useState(false);
  const [rescoreError, setRescoreError] = useState(null);

  const recs = useApi(
    () => api.recommendations('transaction', id),
    [id],
    { immediate: Boolean(id) },
  );

  const data = tx.data;
  const shown = live || data;
  const level = levelFromCategory(shown?.risk_category);
  const tone = toneForLevel(level);

  async function rescore() {
    setRescoring(true);
    setRescoreError(null);
    try {
      setLive(await api.transactionRisk(id));
    } catch (e) {
      setRescoreError(e.message);
    } finally {
      setRescoring(false);
    }
  }

  if (tx.loading) return <Loading label="Loading transaction…" />;
  if (tx.error) return <ErrorBox error={tx.error} onRetry={tx.refetch} />;
  if (!data) return <Empty label="Transaction not found" />;

  return (
    <div className="stack">
      <div className="row wrap" style={{ gap: 10 }}>
        <Link className="btn ghost sm" to="/transactions">
          ‹ Back to explorer
        </Link>
        <span className="mono faint">{data.id}</span>
        <div style={{ flex: 1 }} />
        <button className="btn sm" onClick={rescore} disabled={rescoring}>
          {rescoring ? 'Scoring…' : 'Re-score live (ML layer)'}
        </button>
      </div>

      {rescoreError && <ErrorBox error={rescoreError} />}

      {/* --------------------------------------------------------- summary */}
      <div className="grid grid-3">
        <Card title="Fraud risk" subtitle="XGBoost binary classifier">
          <div className="row" style={{ alignItems: 'flex-end', gap: 12 }}>
            <div className="kpi-value" style={{ color: `var(--${tone})` }}>
              {Number(shown.fraud_score ?? shown.score).toFixed(0)}
            </div>
            <div style={{ paddingBottom: 4 }}>
              <RiskBadge category={shown.risk_category} level={level} />
            </div>
          </div>
          <div style={{ margin: '10px 0' }}>
            <ScoreBar value={shown.fraud_score ?? shown.score} level={level} />
          </div>
          <div className="row wrap" style={{ gap: 6 }}>
            <ModelBadge modelUsed={shown.model_used} status={shown.prediction_status} />
            {shown.confidence != null && (
              <Badge tone="neutral">confidence {(shown.confidence * 100).toFixed(1)}%</Badge>
            )}
            {shown.confidence_method && <Badge tone="neutral">{shown.confidence_method}</Badge>}
          </div>
          <div className="divider" />
          <div className="row wrap" style={{ gap: 8 }}>
            <Badge
              tone={
                shown.decision === 'suspicious'
                  ? 'critical'
                  : shown.decision === 'review_recommended'
                    ? 'warn'
                    : 'ok'
              }
            >
              {titleCase(shown.decision)}
            </Badge>
          </div>
          <Note>
            {shown.decision_note ||
              'A low score is not a certification of legitimacy — it reflects limited fraud evidence in the available features.'}
          </Note>
        </Card>

        <Card title="Transaction" subtitle={dateTime(data.ts)}>
          <div className="grid grid-2" style={{ gap: 10 }}>
            <StatMini value={inr(data.amount)} label="Amount" />
            <StatMini value={titleCase(data.channel)} label="Channel" />
            <StatMini value={data.merchant_category || '—'} label="Merchant category" />
            <StatMini value={data.purpose || '—'} label="Purpose" />
            <StatMini value={data.city || '—'} label="City" />
            <StatMini value={data.relationship || '—'} label="Relationship" />
          </div>
          <div className="divider" />
          <div style={{ fontSize: 12.5 }}>
            <div className="faint" style={{ fontSize: 11 }}>
              Sender
            </div>
            <div className="strong">{data.sender?.name}</div>
            <div className="mono faint">{data.sender?.id}</div>
            <div className="faint" style={{ fontSize: 11, marginTop: 8 }}>
              Receiver
            </div>
            <div className="strong">{data.receiver?.name}</div>
            <div className="mono faint">{data.receiver?.id}</div>
          </div>
          {data.narrative && (
            <>
              <div className="divider" />
              <Note>“{data.narrative}”</Note>
            </>
          )}
        </Card>

        <Card title="Independent signals" subtitle="Anomaly and scam models run separately from fraud">
          <div className="strong" style={{ fontSize: 13, marginBottom: 6 }}>
            Anomaly detection
          </div>
          <div className="row wrap" style={{ gap: 6, marginBottom: 8 }}>
            <Badge tone={shown.anomaly?.is_anomaly ? 'warn' : 'ok'} dot>
              {shown.anomaly?.is_anomaly ? 'Anomalous' : 'Within normal pattern'}
            </Badge>
            <ModelBadge
              modelUsed={shown.anomaly?.model_used}
              status={shown.anomaly?.prediction_status}
            />
          </div>
          {shown.anomaly?.anomaly_score != null && (
            <div style={{ marginBottom: 8 }}>
              <div className="spread" style={{ fontSize: 11.5, marginBottom: 4 }}>
                <span className="faint">Anomaly score</span>
                <span className="strong">{shown.anomaly.anomaly_score.toFixed(1)}/100</span>
              </div>
              <div className="hbar">
                <span
                  style={{
                    width: `${Math.min(100, shown.anomaly.anomaly_score)}%`,
                    background: 'var(--warn)',
                  }}
                />
              </div>
            </div>
          )}
          {shown.anomaly?.explanation && <Note>{shown.anomaly.explanation}</Note>}
          {(shown.anomaly?.drivers || []).length > 0 && (
            <div className="chip-row" style={{ marginTop: 8 }}>
              {shown.anomaly.drivers.map((d) => (
                <span className="tag" key={d}>
                  {d}
                </span>
              ))}
            </div>
          )}

          <div className="divider" />
          <div className="strong" style={{ fontSize: 13, marginBottom: 6 }}>
            Scam classification
          </div>
          <div className="row wrap" style={{ gap: 6 }}>
            <Badge tone="accent">
              {shown.scam?.label || titleCase(shown.scam?.scam_category) || '—'}
            </Badge>
            {shown.scam?.confidence != null && (
              <Badge tone="neutral">{(shown.scam.confidence * 100).toFixed(0)}%</Badge>
            )}
            <ModelBadge modelUsed={shown.scam?.model_used} status={shown.scam?.prediction_status} />
          </div>
          {shown.scam?.explanation && (
            <div style={{ marginTop: 8 }}>
              <Note>{shown.scam.explanation}</Note>
            </div>
          )}
        </Card>
      </div>

      {/* ------------------------------------------------------ explanation */}
      <div className="grid grid-2">
        <Card
          title="Why this score — explanation"
          subtitle={
            shown.model_used === 'xgboost'
              ? 'SHAP contributions from the XGBoost model (computed in the ML layer)'
              : 'Deterministic rule attributions (fallback engine)'
          }
        >
          {shown.explanation && <Explain>{shown.explanation}</Explain>}
          <div style={{ marginTop: 12 }}>
            <FactorList factors={shown.factors || []} />
          </div>
          <Note>
            Factors show what moved the model score. They are computed server-side; the UI never
            derives them.
          </Note>
        </Card>

        <div className="stack">
          <Card
            title="Recommended interventions"
            subtitle="Suggested by the intervention engine for this risk level"
          >
            {recs.loading && <Loading label="Loading recommendations…" />}
            {recs.error && <ErrorBox error={recs.error} onRetry={recs.refetch} />}
            {(recs.data?.recommendations || []).map((r, i) => (
              <div className="list-item" key={i}>
                <Badge
                  tone={
                    r.priority === 'critical'
                      ? 'critical'
                      : r.priority === 'high'
                        ? 'danger'
                        : r.priority === 'medium'
                          ? 'warn'
                          : 'neutral'
                  }
                >
                  {r.priority}
                </Badge>
                <div>
                  <div className="strong" style={{ fontSize: 13 }}>
                    {r.action}
                  </div>
                  <div className="faint" style={{ fontSize: 11.5 }}>
                    {r.description}
                  </div>
                </div>
              </div>
            ))}
            {!recs.loading && !(recs.data?.recommendations || []).length && (
              <Empty label="No recommendations" />
            )}
          </Card>

          {data.dataset_label && (
            <Card
              title="Synthetic dataset ground truth"
              subtitle="Shown only because the demo dataset is synthetic"
            >
              <div className="row wrap" style={{ gap: 8 }}>
                <Badge tone={data.dataset_label.is_fraud ? 'critical' : 'ok'}>
                  {data.dataset_label.is_fraud ? 'Labeled fraud' : 'Labeled legitimate'}
                </Badge>
                {data.dataset_label.scam_category && (
                  <Badge tone="neutral">{titleCase(data.dataset_label.scam_category)}</Badge>
                )}
              </div>
              <div style={{ marginTop: 10 }}>
                <Note>{data.dataset_label.note}</Note>
              </div>
              <div className="mono-block" style={{ marginTop: 10 }}>
                {JSON.stringify({ id: data.id, amount: data.amount, channel: data.channel }, null, 2)}
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
