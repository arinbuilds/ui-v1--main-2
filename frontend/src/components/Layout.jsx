import { createContext, useEffect, useState } from 'react';
import { NavLink, Link, useLocation } from 'react-router-dom';
import { useApi } from '../hooks/useApi.js';
import api from '../api.js';
import Icon from './Icons.jsx';
import { Badge } from './ui.jsx';

export const AppActionContext = createContext({ openScan: () => {}, openPayment: () => {} });

const NAV = [
  { group: 'Your money' },
  { to: '/', label: 'Home', icon: '⌂', end: true },
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
  '/': ['Your money, made clear', 'A simple view of your money and activity'],
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

function ActionOverlay({ overlay, onClose, openPayment }) {
  const [reviewed, setReviewed] = useState(false);
  useEffect(() => {
    const onKeyDown = (event) => event.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  if (!overlay) return null;
  const isScan = overlay.type === 'scan';
  const action = overlay.action || 'Payment';

  return (
    <div className="action-overlay" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className={`action-sheet${isScan ? ' scan-sheet' : ''}`} role="dialog" aria-modal="true" aria-labelledby="action-sheet-title">
        <div className="sheet-handle" />
        {isScan ? (
          <>
            <div className="sheet-heading">
              <div><h2 id="action-sheet-title">Scan any QR</h2><p>Scan a code to start a payment</p></div>
              <button className="sheet-close" type="button" onClick={onClose} aria-label="Close">×</button>
            </div>
            <div className="scan-preview">
              <div className="qr-placeholder" aria-hidden="true">
                <Icon name="scan" size={92} strokeWidth={1.25} />
                <span className="qr-scan-line" />
              </div>
              <span className="scan-corner scan-tl" /><span className="scan-corner scan-tr" />
              <span className="scan-corner scan-bl" /><span className="scan-corner scan-br" />
            </div>
            <p className="sheet-footnote">Camera scanning is not connected in this prototype.</p>
            <button className="sheet-primary" type="button" onClick={() => openPayment('Bank transfer')}>Enter payment details</button>
          </>
        ) : (
          <>
            <div className="sheet-heading">
              <div><h2 id="action-sheet-title">{reviewed ? 'Review payment' : action}</h2><p>{reviewed ? 'Check the details before continuing' : 'Enter the payment details'}</p></div>
              <button className="sheet-close" type="button" onClick={onClose} aria-label="Close">×</button>
            </div>
            {reviewed ? (
              <div className="payment-review">
                <div className="review-check"><Icon name="shield" size={24} /></div>
                <strong>Demo payment preview</strong>
                <p>No money has been moved. Payment processing is not connected to this app.</p>
                <button className="sheet-secondary" type="button" onClick={() => setReviewed(false)}>Edit details</button>
                <button className="sheet-primary" type="button" onClick={onClose}>Done</button>
              </div>
            ) : (
              <form className="payment-form" onSubmit={(event) => { event.preventDefault(); setReviewed(true); }}>
                <label>{action === 'To Mobile' ? 'Mobile number' : 'Recipient or account'}
                  <input autoComplete="off" inputMode={action === 'To Mobile' ? 'tel' : 'text'} placeholder={action === 'To Mobile' ? 'Enter mobile number' : 'Name or account number'} required />
                </label>
                <label>Amount
                  <span className="amount-input"><span>₹</span><input inputMode="decimal" type="number" min="1" step="0.01" placeholder="0.00" required /></span>
                </label>
                <button className="sheet-primary" type="submit">Review payment</button>
                <p className="sheet-footnote">Prototype preview only. This will not send money.</p>
              </form>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function MobileNavigation({ pathname, openScan }) {
  const activeMore = pathname === '/more' || !['/', '/transactions', '/borrowers'].some((route) => route === pathname) && !pathname.startsWith('/transactions/') && !pathname.startsWith('/borrowers/');
  return (
    <>
      <button className="scan-fab" type="button" onClick={openScan}><Icon name="scan" size={21} /> <span>Scan Any QR</span></button>
      <nav className="mobile-nav" aria-label="Main navigation">
        <NavLink to="/" end className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}><Icon name="home" size={21} /><span>Home</span></NavLink>
        <NavLink to="/transactions" className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}><Icon name="activity" size={21} /><span>Activity</span></NavLink>
        <button type="button" className="mobile-nav-item nav-scan" onClick={openScan} aria-label="Scan QR"><span className="nav-scan-icon"><Icon name="scan" size={22} /></span><span>Scan</span></button>
        <NavLink to="/borrowers" className={({ isActive }) => `mobile-nav-item${isActive ? ' active' : ''}`}><Icon name="wallet" size={21} /><span>Accounts</span></NavLink>
        <NavLink to="/more" className={`mobile-nav-item${activeMore ? ' active' : ''}`}><Icon name="more" size={22} /><span>More</span></NavLink>
      </nav>
    </>
  );
}

export default function Layout({ children }) {
  const { pathname } = useLocation();
  const [overlay, setOverlay] = useState(null);
  const base = '/' + (pathname.split('/')[1] || '');
  const [title, sub] = TITLES[base] || TITLES['/'];
  const isHome = pathname === '/';
  const openScan = () => setOverlay({ type: 'scan' });
  const openPayment = (action) => setOverlay({ type: 'payment', action });
  const closeOverlay = () => setOverlay(null);

  return (
    <AppActionContext.Provider value={{ openScan, openPayment }}>
      <div className={`shell${isHome ? ' home-shell' : ''}`}>
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">
              <div className="brand-logo">FS</div>
              <div><div className="brand-name">FINTECHSICO</div><div className="brand-sub">Financial Risk Intelligence</div></div>
            </div>
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
            <div className="note" style={{ marginTop: 10 }}>Scores, bands and explanations are computed by the Python ML layer. This UI only renders API responses.</div>
          </div>
        </aside>

        <div className="main">
          <header className={`topbar${isHome ? ' home-topbar' : ''}`}>
            {isHome ? (
              <>
                <Link to="/borrowers" className="profile-dot" aria-label="Open accounts">F</Link>
                <Link to="/" className="home-brand"><strong>FINTECHSICO</strong><small>MONEY & ACTIVITY</small></Link>
                <div className="topbar-spacer" />
                <Link className="topbar-icon" to="/transactions" aria-label="Search transactions"><Icon name="search" size={23} /></Link>
                <Link className="topbar-icon has-notice" to="/alerts" aria-label="View alerts"><Icon name="message" size={23} /></Link>
              </>
            ) : (
              <>
                <div><h1>{title}</h1><div className="sub">{sub}</div></div>
                <div className="topbar-spacer" />
                <HealthPill />
              </>
            )}
          </header>
          <main className={`content${isHome ? ' home-content' : ''}`}>{children}</main>
        </div>
      </div>
      <MobileNavigation pathname={pathname} openScan={openScan} />
      <ActionOverlay key={overlay ? `${overlay.type}-${overlay.action || ''}` : 'closed'} overlay={overlay} onClose={closeOverlay} openPayment={openPayment} />
    </AppActionContext.Provider>
  );
}
