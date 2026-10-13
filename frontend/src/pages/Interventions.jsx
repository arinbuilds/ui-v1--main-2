import { useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../api.js';
import { useApi } from '../hooks/useApi.js';
import {
  Card,
  Badge,
  ModelBadge,
  Loading,
  ErrorBox,
  Empty,
  Note,
  StatMini,
} from '../components/ui.jsx';
import { inr, num, titleCase } from '../lib/format.js';

const STATUS_TONE = { 'Pending': 'warn', 'In Progress': 'accent', 'Completed': 'ok' };

export default function Interventions() {
  const [subject, setSubject] = useState('transaction');
  const [subjectId, setSubjectId] = useState('');
  const [cm, setCm] = useState({ category: 'fraud', action: 'flag', priority: 'high' });
  const [creating, setCreating] = useState(false);

  // dashboards context
  const dashboard = useApi(() => api.dashboard(), []);
  const list = useApi(
    () => api.interventions({ limit: 300 }),
    [],
    { immediate: true },
  );
  const history = useApi(() => api.interventionHistory({ limit: 120 }), [], { immediate: true });

  const suggestions = useApi(
    () => api.recommendations(subject, subjectId),
    [subject, subjectId],
    { immediate: false },
  );

  async function create() {
    if (!cm.action || !cm.title) return;
    setCreating(true);
    try {
      const payload = {
        category: cm.category,
        action: cm.action,
        title: cm.title,
        priority: cm.priority,
        subject_type: subject,
        subject_id: subjectId,
      };
      await api.createIntervention(payload);
      await list.refetch();
      await history.refetch();
      setCm({ category: 'fraud', action: 'flag', priority: 'high' });
      setSubjectId('');
    } catch (e) {
      alert(e.message);
    } finally {
      setCreating(false);
    }
  }

  const counts = dashboard.data?.interventions || {};

  return (
    <div className="stack">
      <div className="grid grid-4">
        <Card title="Open">
          <div className="kpi-value" style={{ color: 'var(--warn)' }}>
            {num(counts.Pending ?? 0)}
          </div>
        </Card>
        <Card title="In progress">
          <div className="kpi-value">{num(counts['In Progress'] ?? 0)}</div>
        </Card>
        <Card title="Completed">
          <div className="kpi-value" style={{ color: 'var(--ok)' }}>
            {num(counts.Completed ?? 0)}
          </div>
        </Card>
        <Card title="Total">
          <div className="kpi-value">{num(dashboard.data?.total ?? 0)}</div>
        </Card>
      </div>

      <Card title="Create intervention" subtitle="Assign a recommended action to a subject">
        <div className="controls">
          <select
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            style={{ maxWidth: 140 }}
          >
            <option value="transaction">Transaction</option>
            <option value="borrower">Borrower</option>
          </select>
          <select
            value={cm.category}
            onChange={(e) => setCm((c) => ({ ...c, category: e.target.value }))}
            style={{ maxWidth: 140 }}
          >
            <option value="fraud">Fraud</option>
            <option value="loan">Loan</option>
          </select>
          <input
            list="action-options"
            placeholder="Action"
            value={cm.action}
            onChange={(e) => setCm((c) => ({ ...c, action: e.target.value }))}
            style={{ maxWidth: 360, flex: 1 }}
          />
          <datalist id="action-options">
            <option value="Flag for review" />
            <option value="Warn the customer" />
            <option value="Investigate connected accounts" />
            <option value="Trace money flow" />
            <option value="Contact borrower" />
            <option value="Offer review of repayment terms" />
            <option value="Consider restructuring options" />
          </datalist>
          <select
            value={cm.priority}
            onChange={(e) => setCm((c) => ({ ...c, priority: e.target.value }))}
            style={{ maxWidth: 130 }}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
            <option value="critical">Critical</option>
          </select>
          <input
            placeholder="Title"
            value={cm.title}
            onChange={(e) => setCm((c) => ({ ...c, title: e.target.value }))}
            style={{ maxWidth: 260, flex: 1 }}
          />
          <button
            className="btn sm"
            onClick={create}
            disabled={creating || !cm.action || !cm.title}
          >
            {creating ? 'Creating…' : 'Create'}
          </button>
        </div>
        <Note>
          The recommended action list below is fetched for the subject you typed; it is only a
          suggestion. Creating an intervention is a manual analyst action.
        </Note>
      </Card>

      <Card
        title="Recommendations"
        subtitle={`Suggestions for ${subject}${subjectId ? `: ${subjectId}` : ''}`}
      >
        {suggestions.loading && <Loading />}
        {suggestions.data?.recommendations && (
          suggestions.data.recommendations.map((r, i) => (
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
          ))
        )}
        {suggestions.error && <ErrorBox error={suggestions.error} onRetry={suggestions.refetch} />}
        {!suggestions.loading && suggestions.data && !suggestions.data.recommendations?.length && (
          <Empty label="No recommendations for this subject" />
        )}
      </Card>

      {(list.data?.items || []).length === 0 && (
        <Card title="Intervention queue">
          <Empty label="No interventions yet" />
        </Card>
      )}

      <Card
        title="Intervention queue"
        subtitle="Row shows the current workflow state; history is logged on every change"
      >
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Subject</th>
                <th>Action</th>
                <th>Priority</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {(list.data?.items || []).map((it) => (
                <tr key={it.id}>
                  <td>
                    {it.subject_type === 'transaction' ? (
                      <Link className="mono" to={`/transactions/${it.subject_id}`}>
                        {it.subject_id}
                      </Link>
                    ) : (
                      <Link className="mono" to={`/borrowers/${it.subject_id}`}>
                        {it.subject_id}
                      </Link>
                    )}
                    <div className="faint" style={{ fontSize: 11 }}>
                      {it.category}
                    </div>
                  </td>
                  <td>{it.action}</td>
                  <td className="nowrap">
                    <Badge
                      tone={
                        it.priority === 'critical'
                          ? 'critical'
                          : it.priority === 'high'
                            ? 'danger'
                            : it.priority === 'medium'
                              ? 'warn'
                              : 'neutral'
                      }
                    >
                      {it.priority}
                    </Badge>
                  </td>
                  <td>
                    <Badge tone={STATUS_TONE[it.status] || 'neutral'}>{it.status}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card
        title="Change history"
        subtitle="Every status change and outcome is appended to the intervention record"
      >
        {history.loading && <Loading />}
        {history.error && <ErrorBox error={history.error} onRetry={history.refetch} />}
        {!history.loading && history.data?.events && history.data.events.length === 0 && (
          <Empty label="No changes recorded yet" />
        )}
        {(history.data?.events || []).map((e, i) => (
          <div key={`${e.intervention_id}-${e.at || i}-${i}`} className="list-item">
            <Badge tone={STATUS_TONE[e.to] || 'neutral'}>{e.to}</Badge>
            <div style={{ minWidth: 0 }}>
              <div className="mono" style={{ fontSize: 11.5 }}>
                #{e.intervention_id} · {e.action}
              </div>
              <div className="faint" style={{ fontSize: 11 }}>
                {new Date(e.at || '').toLocaleString('en-IN')} · {e.event}
              </div>
              {e.note && <div className="faint" style={{ fontSize: 10.5 }}>{e.note}</div>}
            </div>
          </div>
        ))}
      </Card>
    </div>
  );
}
