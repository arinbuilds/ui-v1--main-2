import { NavLink, Link, useLocation } from 'react-router-dom';
import { useApi } from '../hooks/useApi.js';
import api from '../api.js';
import Icon from './Icons.jsx';
import { Badge } from './ui.jsx';

const NAV = [
  { group: 'Workspace' },
  { to: '/', label: 'Command Center', icon: '⌂', end: true },
  { to: '/transactions', label: 'Transactions', icon: '⇄' },
  { to: '/borrowers', label: 'Borrowers & Loans', icon: '◍' },
  { group: 'Risk intelligence' },
  { to: '/dashboard', label: 'Risk overview', icon: '◧' },
  { to: '/graph', label: 'Money-Flow Graph', icon: '◈' },
  { to: '/alerts', label: 'Alerts', icon: '◉' },
  { to: '/interventions', label: 'Interventions', icon: '✓' },
  { to: '/models', label: 'Model Health', icon: '⌁' },
];

const TITLES = {
  '/': ['FraudShield Command Center', 'A real-time view of financial risk signals'],
  '/dashboard': ['Risk Operations Dashboard', 'Fraud, anomaly and repayment-risk intelligence'],
  '/transactions': ['Transaction Explorer', 'Score, explain and investigate transactions'],
  '/borrowers': ['Borrowers & Loans', 'Repayment risk, SHAP explanations and loan usage'],
  '/graph': ['Money-Flow Graph', 'NetworkX account tracing and circular-flow detection'],
  '/alerts': ['Alert Queue', 'Fraud, anomaly and early-warning alerts'],
  '/interventions': ['Interventions', 'Recommended actions, workflow and history'],
  '/models': ['Model Health', 'Loaded artifacts, fallback state and thresholds'],
  '/more': ['More tools', 'More account and risk tools'],
};

function HealthPill() {
  const { data } = useApi(() => api.health(), []);
  if (!data) return <Badge tone="neutral" dot>connecting…</Badge>;
  const s = data.model_summary || {};
  if (s.fallback_in_use) return <Badge tone="warn" dot>Fallback mode</Badge>;
  return <Badge tone={data.status === 'ok' ? 'ok' : 'warn'} dot>{data.status === 'ok' ? 'All models live' : data.status}</Badge>;
}

function MobileNavigation({ pathname }) {
  const activeMore = pathname === '/more' || !['/', '/transactions', '/borrowers', '/alerts'].some((route) => route === pathname) && !pathname.startsWith('/transactions/') && !pathname.startsWith('/borrowers/');
  return (
    <nav className="mobile-nav" aria-label="Main navigation">
      <NavLink to="/" end className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}><Icon name="home" size={20} /><span>Home</span></NavLink>
      <NavLink to="/transactions" className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}><Icon name="activity" size={20} /><span>Activity</span></NavLink>
      <NavLink to="/alerts" className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}><Icon name="shield" size={20} /><span>Alerts</span></NavLink>
      <NavLink to="/borrowers" className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}><Icon name="wallet" size={20} /><span>Borrowers</span></NavLink>
      <NavLink to="/more" className={`mobile-nav-item${activeMore ? ' active' : ''}`}><Icon name="more" size={21} /><span>More</span></NavLink>
    </nav>
  );
}

export default function Layout({ children }) {
  const { pathname } = useLocation();
  const base = '/' + (pathname.split('/')[1] || '');
  const [title, sub] = TITLES[base] || TITLES['/'];

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <Link to="/" className="brand-mark">
            <div className="brand-logo">FS</div>
            <div><div className="brand-name">FINTECHSICO</div><div className="brand-sub">FraudShield Intelligence</div></div>
          </Link>
        </div>
        <nav className="nav">
          {NAV.map((item, i) => item.group ? (
            <div className="nav-group" key={`g-${i}`}>{item.group}</div>
          ) : (
            <NavLink key={item.to} to={item.to} end={item.end} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
              <span className="nav-icon">{item.icon}</span>{item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <HealthPill />
          <div className="note" style={{ marginTop: 10 }}>Risk scores and model explanations are provided by the Python analytics API.</div>
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div><h1>{title}</h1><div className="sub">{sub}</div></div>
          <div className="topbar-spacer" />
          <span className="environment-tag"><span /> DEMO ENVIRONMENT</span>
          <HealthPill />
        </header>
        <main className="content">{children}</main>
      </div>
      <MobileNavigation pathname={pathname} />
    </div>
  );
}
