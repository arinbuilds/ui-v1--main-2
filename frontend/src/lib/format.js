/** Formatting helpers — presentation only, never risk logic. */

export function inr(value, { compact = false } = {}) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '—';
  if (compact) {
    if (Math.abs(n) >= 1e7) return `₹${(n / 1e7).toFixed(2)} Cr`;
    if (Math.abs(n) >= 1e5) return `₹${(n / 1e5).toFixed(2)} L`;
    if (Math.abs(n) >= 1e3) return `₹${(n / 1e3).toFixed(1)}K`;
  }
  return `₹${n.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
}

export function num(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toLocaleString('en-IN') : '—';
}

export function pct(value, digits = 1) {
  const n = Number(value);
  return Number.isFinite(n) ? `${(n * 100).toFixed(digits)}%` : '—';
}

export function score(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n.toFixed(0) : '—';
}

export function shortDate(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' });
}

export function dateTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function relative(ts) {
  if (!ts) return '—';
  const d = new Date(ts).getTime();
  if (Number.isNaN(d)) return ts;
  const diff = Date.now() - d;
  const mins = Math.round(diff / 60000);
  if (Math.abs(mins) < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (Math.abs(hours) < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  return `${days}d ago`;
}

/**
 * Map a backend risk band `level` to a visual tone.
 * The band itself (thresholds/labels) always comes from the API.
 */
export const LEVEL_TONE = {
  low: 'ok',
  moderate: 'warn',
  high: 'danger',
  critical: 'critical',
};

export function toneForLevel(level) {
  return LEVEL_TONE[level] || 'neutral';
}

/**
 * Derive a visual level from a backend-provided risk category label.
 * The thresholds themselves live only in the backend (risk_config.RISK_BANDS);
 * this maps the returned label — never a numeric score — to a tone.
 */
const CATEGORY_LEVEL = {
  'Low Risk': 'low',
  'Moderate Risk': 'moderate',
  'High Risk': 'high',
  'Critical Risk': 'critical',
};

export function levelFromCategory(category) {
  return CATEGORY_LEVEL[category] || 'neutral';
}

export function titleCase(value) {
  if (!value) return '—';
  return String(value)
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());
}
