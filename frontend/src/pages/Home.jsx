import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Area, AreaChart, ResponsiveContainer, Tooltip } from 'recharts';
import api from '../api.js';
import Icon from '../components/Icons.jsx';
import { inr, num } from '../lib/format.js';

const refreshEveryMs = 30_000;

function StatCard({ label, value, detail, icon, tone = 'blue', to }) {
  const content = <>
    <div className="intel-stat-top"><span className={`intel-stat-icon ${tone}`}><Icon name={icon} size={19} /></span><span className="intel-stat-label">{label}</span></div>
    <strong className="intel-stat-value">{value}</strong>
    <span className="intel-stat-detail">{detail}</span>
  </>;
  return to ? <Link className="intel-stat" to={to}>{content}<span className="intel-stat-arrow"><Icon name="arrow" size={16} /></span></Link> : <div className="intel-stat">{content}</div>;
}

export default function Home() {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let mounted = true;
    const refresh = async () => {
      if (mounted) setRefreshing(true);
      try {
        const result = await api.dashboard();
        if (!mounted) return;
        setData(result);
        setError('');
        setUpdatedAt(new Date());
      } catch (err) {
        if (mounted) setError(err.message || 'Could not reach the analytics service');
      } finally {
        if (mounted) setRefreshing(false);
      }
    };
    refresh();
    const timer = window.setInterval(refresh, refreshEveryMs);
    return () => { mounted = false; window.clearInterval(timer); };
  }, []);

  const k = data?.kpis || {};
  const trends = data?.trends || [];
  const models = data?.model_status || {};
  const fallback = Object.values(models).some((model) => model && (model.forced_fallback || !model.loaded));

  return (
    <div className="intel-home">
      <section className="intel-hero">
        <div className="intel-hero-copy">
          <div className="intel-eyebrow"><span className="intel-live-dot" /> FINTECHSICO <span className="intel-eyebrow-divider">/</span> FRAUDSHIELD</div>
          <h2>See the signal.<br /><span>Act with confidence.</span></h2>
          <p>One focused command center for suspicious transactions, anomaly patterns and repayment risk.</p>
          <div className="intel-hero-actions">
            <Link className="intel-primary-btn" to="/dashboard">Open risk overview <Icon name="arrow" size={17} /></Link>
            <Link className="intel-secondary-btn" to="/alerts">Review alert queue <Icon name="shield" size={16} /></Link>
          </div>
          <div className="intel-demo-note"><span className="intel-demo-mark">◆</span> DEMO ENVIRONMENT <span>·</span> Synthetic sample data</div>
        </div>
        <div className="intel-orbit" aria-hidden="true">
          <div className="intel-orbit-grid" />
          <div className="intel-ring ring-a" /><div className="intel-ring ring-b" /><div className="intel-ring ring-c" />
          <div className="intel-orbit-track"><span className="intel-orbit-node node-a" /><span className="intel-orbit-node node-b" /><span className="intel-orbit-node node-c" /></div>
          <div className="intel-core"><Icon name="shield" size={43} strokeWidth={1.35} /><span>RISK<br />ENGINE</span></div>
          <div className="intel-orbit-caption"><span className="intel-live-dot" /> SIGNAL MONITORING</div>
          <div className="intel-orbit-coord">28.6139° N&nbsp;&nbsp; 77.2090° E</div>
        </div>
        <div className="intel-hero-index">01 <span>/ 04</span></div>
      </section>

      <section className="intel-section">
        <div className="intel-section-heading">
          <div><div className="intel-section-kicker">OPERATIONS SNAPSHOT</div><h3>Risk at a glance</h3></div>
          <div className={`intel-refresh ${error ? 'offline' : ''}`}><span className={`intel-live-dot ${error ? 'offline' : ''}`} />{error ? 'API unavailable' : refreshing ? 'Syncing' : 'Live monitoring'}<span className="intel-refresh-time">{updatedAt ? `· ${updatedAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}</span></div>
        </div>
        {error && <div className="intel-inline-error">{error} <button type="button" onClick={() => window.location.reload()}>Reload</button></div>}
        <div className="intel-stats-grid">
          <StatCard label="Transactions analyzed" value={data ? num(k.transactions_total) : '—'} detail={`${data ? inr(k.transaction_volume, { compact: true }) : '—'} total volume`} icon="activity" tone="blue" to="/transactions" />
          <StatCard label="Suspicious activity" value={data ? num(k.suspicious_transactions) : '—'} detail={`${data ? num(k.review_transactions) : '—'} flagged for review`} icon="scan" tone="coral" to="/transactions" />
          <StatCard label="Open alerts" value={data ? num(k.open_alerts) : '—'} detail="Awaiting analyst action" icon="bell" tone="amber" to="/alerts" />
          <StatCard label="High-risk borrowers" value={data ? num(k.high_risk_borrowers) : '—'} detail={`${data ? num(k.critical_borrowers) : '—'} in critical band`} icon="wallet" tone="violet" to="/borrowers" />
        </div>
      </section>

      <section className="intel-lower-grid">
        <div className="intel-panel intel-trend-panel">
          <div className="intel-panel-heading"><div><div className="intel-section-kicker">MODEL ACTIVITY</div><h3>Transaction signal</h3></div><Link to="/dashboard" className="intel-text-link">Full analytics <Icon name="arrow" size={15} /></Link></div>
          <p className="intel-panel-description">Weekly transaction volume and average fraud score from the analytics service.</p>
          {trends.length ? <div className="intel-chart-wrap"><ResponsiveContainer width="100%" height={184}><AreaChart data={trends}>
            <defs><linearGradient id="intelChartGlow" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5ce1e6" stopOpacity={0.32} /><stop offset="100%" stopColor="#5ce1e6" stopOpacity={0} /></linearGradient></defs>
            <Tooltip contentStyle={{ background: '#101b2a', border: '1px solid #263d50', borderRadius: 10, color: '#e7f4f6', fontSize: 11 }} labelStyle={{ color: '#89a6b2' }} />
            <Area type="monotone" dataKey="tx_count" name="Transactions" stroke="#5ce1e6" strokeWidth={2.5} fill="url(#intelChartGlow)" activeDot={{ r: 4, fill: '#adfbff', stroke: '#5ce1e6' }} />
          </AreaChart></ResponsiveContainer></div> : <div className="intel-chart-empty">{data ? 'No trend data returned yet.' : 'Connecting to the analytics service…'}</div>}
          <div className="intel-chart-legend"><span><i /> Transaction count</span><span className="intel-chart-period">WEEKLY AGGREGATION</span></div>
        </div>
        <div className="intel-panel intel-health-panel">
          <div className="intel-panel-heading"><div><div className="intel-section-kicker">DECISION SUPPORT</div><h3>System readiness</h3></div><span className={`intel-readiness ${!data || error || fallback ? 'caution' : 'ready'}`}><i />{error ? 'Offline' : !data ? 'Connecting' : fallback ? 'Review' : 'Ready'}</span></div>
          <p className="intel-panel-description">Model state and review workload, reported by your local API.</p>
          <div className="intel-health-list">
            <div className="intel-health-row"><span className="intel-health-icon cyan"><Icon name="chart" size={17} /></span><span><strong>Average fraud score</strong><small>Across scored transactions</small></span><b>{data ? `${k.fraud_score_avg ?? '—'}/100` : '—'}</b></div>
            <div className="intel-health-row"><span className="intel-health-icon purple"><Icon name="wallet" size={17} /></span><span><strong>Borrowers monitored</strong><small>Repayment score available</small></span><b>{data ? num(k.borrowers_total) : '—'}</b></div>
            <div className="intel-health-row"><span className="intel-health-icon orange"><Icon name="shield" size={17} /></span><span><strong>Pending interventions</strong><small>Recommended analyst actions</small></span><b>{data ? num(k.pending_interventions) : '—'}</b></div>
          </div>
          <div className="intel-health-foot"><span className={`intel-live-dot ${fallback ? 'offline' : ''}`} />{error ? 'Waiting for API connection' : fallback ? 'One or more models use fallback mode' : 'Analytics API connected'}<Link to="/models">Model details <Icon name="arrow" size={14} /></Link></div>
        </div>
      </section>
      <footer className="intel-footer"><span>FRAUDSHIELD <span>·</span> RISK INTELLIGENCE</span><span>Refreshes every 30 seconds <span>·</span> Demo data only</span></footer>
    </div>
  );
}
