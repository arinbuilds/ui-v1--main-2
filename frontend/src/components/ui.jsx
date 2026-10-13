import { toneForLevel, score as fmtScore } from '../lib/format.js';

/* ------------------------------------------------------------------ card */
export function Card({ title, subtitle, action, children, className = '', bodyClass = '' }) {
  return (
    <section className={`card ${className}`}>
      {(title || action) && (
        <header className="card-head">
          {title && (
            <div>
              <div className="card-title">{title}</div>
              {subtitle && <div className="card-sub">{subtitle}</div>}
            </div>
          )}
          <div className="card-spacer" />
          {action}
        </header>
      )}
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

/* ------------------------------------------------------------------ badges */
export function Badge({ tone = 'neutral', children, dot = false }) {
  return (
    <span className={`badge ${tone}`}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}

export function RiskBadge({ category, level }) {
  return <Badge tone={toneForLevel(level)}>{category || '—'}</Badge>;
}

/**
 * Model provenance badge.  The `model_used` / `prediction_status` values are
 * produced by the backend — the UI only renders them.
 */
export function ModelBadge({ modelUsed, status }) {
  if (!modelUsed) return <Badge>unknown</Badge>;
  const isFallback = modelUsed === 'fallback' || status === 'fallback';
  const tone = isFallback ? 'warn' : 'accent';
  const label =
    {
      xgboost: 'XGBoost',
      isolation_forest: 'Isolation Forest',
      rule_engine: 'Rule engine',
      fallback: 'Fallback',
    }[modelUsed] || modelUsed;
  return (
    <Badge tone={tone} dot>
      {label}
      {isFallback ? ' · fallback' : ''}
    </Badge>
  );
}

/* ------------------------------------------------------------------ score */
export function ScoreBar({ value, level }) {
  const n = Math.max(0, Math.min(100, Number(value) || 0));
  return (
    <div className="score-bar">
      <span className={`fill-${toneForLevel(level)}`} style={{ width: `${n}%` }} />
    </div>
  );
}

export function ScoreCell({ value, level }) {
  return (
    <div className="score-cell">
      <span className="score-num">{fmtScore(value)}</span>
      <div style={{ flex: 1, minWidth: 60 }}>
        <ScoreBar value={value} level={level} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ kpi */
export function Kpi({ label, value, foot, tone, children }) {
  return (
    <div className="card kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-row">
        <div className="kpi-value" style={tone ? { color: `var(--${tone})` } : undefined}>
          {value}
        </div>
        {children}
      </div>
      {foot && <div className="kpi-foot">{foot}</div>}
    </div>
  );
}

/* ------------------------------------------------------------------ states */
export function Loading({ label = 'Loading…' }) {
  return (
    <div className="loading">
      <span className="spinner" /> <span style={{ marginLeft: 8 }}>{label}</span>
    </div>
  );
}

export function ErrorBox({ error, onRetry }) {
  return (
    <div className="error-box">
      <div style={{ marginBottom: onRetry ? 10 : 0 }}>⚠ {error}</div>
      {onRetry && (
        <button className="btn ghost sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function Empty({ label = 'No data' }) {
  return <div className="empty">{label}</div>;
}

/* ------------------------------------------------------------------ factors */
/**
 * Renders backend-provided explanation factors (SHAP values or rule
 * attributions).  No scoring happens here.
 */
export function FactorList({ factors = [], emptyLabel = 'No contributing factors returned.' }) {
  if (!factors.length) return <div className="empty">{emptyLabel}</div>;
  const max = Math.max(...factors.map((f) => Math.abs(f.contribution || 0)), 0.0001);
  return (
    <div>
      {factors.map((f, i) => {
        const up = f.direction === 'increase';
        const width = (Math.abs(f.contribution || 0) / max) * 100;
        return (
          <div className="factor" key={`${f.feature}-${i}`}>
            <div>
              <div className="factor-label">{f.label || f.feature}</div>
              <div className="factor-value">
                {f.value !== undefined && f.value !== '' ? f.value : '—'}
                <span className="faint"> · {f.feature}</span>
              </div>
            </div>
            <div>
              <div className={`factor-contrib ${up ? 'contrib-up' : 'contrib-down'}`}>
                {up ? '▲' : '▼'} {Math.abs(f.contribution || 0).toFixed(2)}
              </div>
              <div className="hbar" style={{ marginTop: 4 }}>
                <span
                  style={{
                    width: `${width}%`,
                    background: up ? 'var(--critical)' : 'var(--ok)',
                  }}
                />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

/* ------------------------------------------------------------------ misc */
export function StatMini({ value, label }) {
  return (
    <div className="stat-mini">
      <div className="v">{value}</div>
      <div className="l">{label}</div>
    </div>
  );
}

export function Explain({ children }) {
  return <div className="explain">{children}</div>;
}

export function Note({ children }) {
  return <div className="note">{children}</div>;
}
