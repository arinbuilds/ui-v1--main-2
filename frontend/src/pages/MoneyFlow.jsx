import { useState } from 'react';
import api from '../api.js';
import { useApi } from '../hooks/useApi.js';
import MoneyFlowGraph from '../components/MoneyFlowGraph.jsx';
import {
  Card,
  Badge,
  Loading,
  ErrorBox,
  Empty,
  Note,
  StatMini,
} from '../components/ui.jsx';
import { inr, num, dateTime, titleCase } from '../lib/format.js';

export default function MoneyFlow() {
  const [root, setRoot] = useState('');
  const [depth, setDepth] = useState(2);
  const [minAmount, setMinAmount] = useState('');
  const [selectedNode, setSelectedNode] = useState(null);
  const [selectedEdge, setSelectedEdge] = useState(null);

  const accounts = useApi(() => api.graphAccounts(), []);
  const flow = useApi(
    () =>
      api.moneyFlow({
        account_id: root || undefined,
        depth,
        min_amount: minAmount === '' ? undefined : minAmount,
      }),
    [root, depth, minAmount],
  );

  const trace = useApi(
    () => api.accountTrace(selectedNode),
    [selectedNode],
    { immediate: Boolean(selectedNode) },
  );

  const stats = flow.data?.stats || {};

  return (
    <div className="stack">
      <Card
        title="Money-flow controls"
        subtitle="Graph construction, cycle detection and scoring all happen in the NetworkX service"
        action={
          <button className="btn ghost sm" onClick={flow.refetch}>
            Reload graph
          </button>
        }
      >
        <div className="controls">
          <select value={root} onChange={(e) => setRoot(e.target.value)} style={{ maxWidth: 320 }}>
            <option value="">Full network (all accounts)</option>
            {(accounts.data?.items || []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} — {a.role} ({a.id})
              </option>
            ))}
          </select>
          <select value={depth} onChange={(e) => setDepth(Number(e.target.value))}>
            {[1, 2, 3, 4].map((d) => (
              <option key={d} value={d}>
                Depth {d}
              </option>
            ))}
          </select>
          <input
            type="number"
            placeholder="Min amount"
            value={minAmount}
            onChange={(e) => setMinAmount(e.target.value)}
            style={{ width: 140 }}
          />
          {root && (
            <button className="btn ghost sm" onClick={() => setRoot('')}>
              Clear root
            </button>
          )}
        </div>

        <div className="grid grid-4" style={{ gap: 12 }}>
          <StatMini value={num(stats.node_count)} label="Nodes" />
          <StatMini value={num(stats.edge_count)} label="Edges" />
          <StatMini value={inr(stats.total_flow, { compact: true })} label="Total flow" />
          <StatMini value={num(stats.suspicious_cycles)} label="Suspicious cycles" />
        </div>

        <div className="legend" style={{ marginTop: 12 }}>
          <span>
            <i style={{ background: '#4f8cff' }} /> Individual account
          </span>
          <span>
            <i style={{ background: '#8a5cff' }} /> Business
          </span>
          <span>
            <i style={{ background: '#f0b429' }} /> Has anomalies (Isolation Forest)
          </span>
          <span>
            <i style={{ background: '#ff4d6d' }} /> High fraud risk / suspicious cycle edge
          </span>
        </div>
      </Card>

      {flow.error && <ErrorBox error={flow.error} onRetry={flow.refetch} />}
      {flow.loading && !flow.data && <Loading label="Building graph…" />}

      <div className="grid-3" style={{ gridTemplateColumns: 'minmax(0, 2.2fr) minmax(0, 1fr)' }}>
        <Card title="Network" subtitle="Click a node to trace an account; click an edge to inspect flows">
          {flow.data && (flow.data.nodes || []).length > 0 ? (
            <MoneyFlowGraph
              payload={flow.data}
              onSelectNode={setSelectedNode}
              onSelectEdge={setSelectedEdge}
            />
          ) : (
            !flow.loading && <Empty label="No graph data" />
          )}
        </Card>

        <div className="stack">
          {selectedEdge && (
            <Card title="Selected edge" subtitle={`${selectedEdge.source} → ${selectedEdge.target}`}>
              <div className="grid grid-2" style={{ gap: 10 }}>
                <StatMini value={inr(selectedEdge.amount, { compact: true })} label="Total amount" />
                <StatMini value={selectedEdge.count} label="Transactions" />
                <StatMini value={selectedEdge.max_fraud_score} label="Max fraud score" />
                <StatMini value={selectedEdge.anomaly_count} label="Anomalies" />
              </div>
              <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
                {selectedEdge.in_suspicious_cycle && (
                  <Badge tone="critical">Part of a suspicious cycle</Badge>
                )}
                <Badge tone="neutral">{dateTime(selectedEdge.last_ts)}</Badge>
              </div>
            </Card>
          )}

          <Card
            title={selectedNode ? 'Account trace' : 'Select an account'}
            subtitle={selectedNode || 'Click any node in the graph'}
          >
            {!selectedNode && <Empty label="No account selected" />}
            {trace.loading && <Loading />}
            {trace.error && <ErrorBox error={trace.error} onRetry={trace.refetch} />}
            {trace.data && (
              <>
                <div className="strong" style={{ fontSize: 14 }}>
                  {trace.data.account?.label}
                </div>
                <div className="faint mono" style={{ fontSize: 11 }}>
                  {trace.data.account?.id} · {trace.data.account?.bank} · {trace.data.account?.city}
                </div>
                <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>
                  <Badge tone="neutral">{titleCase(trace.data.account?.role)}</Badge>
                  <Badge tone="neutral">{titleCase(trace.data.account?.entity_type)}</Badge>
                </div>
                <div className="divider" />
                <div className="grid grid-2" style={{ gap: 10 }}>
                  <StatMini value={inr(trace.data.in_total, { compact: true })} label="Inflow" />
                  <StatMini value={inr(trace.data.out_total, { compact: true })} label="Outflow" />
                  <StatMini value={num(trace.data.tx_count)} label="Transactions" />
                  <StatMini value={num((trace.data.connected_accounts || []).length)} label="Counterparties" />
                </div>

                {(trace.data.cycles || []).length > 0 && (
                  <>
                    <div className="divider" />
                    <div className="strong" style={{ fontSize: 13, marginBottom: 6 }}>
                      Cycles involving this account
                    </div>
                    {trace.data.cycles.map((c, i) => (
                      <div className="list-item" key={i}>
                        <Badge tone={c.suspicious ? 'critical' : 'neutral'}>
                          {c.suspicious ? 'suspicious' : 'review'}
                        </Badge>
                        <div>
                          <div className="mono" style={{ fontSize: 11.5 }}>
                            {c.labels?.join(' → ')}
                          </div>
                          <div className="faint" style={{ fontSize: 11 }}>
                            {inr(c.total_amount, { compact: true })} · {c.duration_hours}h · score{' '}
                            {c.cycle_score}
                          </div>
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </>
            )}
          </Card>

          <Card title="Suspicious cycles" subtitle="Bounded NetworkX cycle detection">
            {(flow.data?.cycles || []).length === 0 && <Empty label="No cycles detected" />}
            {(flow.data?.cycles || []).map((c, i) => (
              <div className="list-item" key={i}>
                <Badge tone={c.suspicious ? 'critical' : 'neutral'}>
                  {c.suspicious ? 'suspicious' : 'review'}
                </Badge>
                <div style={{ minWidth: 0 }}>
                  <div className="mono" style={{ fontSize: 11.5 }}>
                    {c.labels?.join(' → ')}
                  </div>
                  <div className="faint" style={{ fontSize: 11 }}>
                    {inr(c.total_amount, { compact: true })} over {c.duration_hours}h · score{' '}
                    {c.cycle_score}
                  </div>
                  {(c.reasons || []).map((r, j) => (
                    <div className="faint" key={j} style={{ fontSize: 11 }}>
                      • {r}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <Note>
              Cycle detection and scoring are performed with NetworkX in the Python services layer.
              The UI renders the results verbatim.
            </Note>
          </Card>
        </div>
      </div>
    </div>
  );
}
