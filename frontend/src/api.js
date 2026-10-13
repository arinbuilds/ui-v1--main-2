/**
 * API client — the ONLY place React talks to the backend.
 *
 * Every risk score, threshold, category and explanation is produced by the
 * Python services/ML layer and returned by FastAPI.  The frontend never
 * computes a score, never re-derives a risk band and never fabricates an
 * ML output.
 */
const BASE = import.meta.env.VITE_API_BASE || '/api';

async function request(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(`${BASE}${path}`, {
    method,
    signal,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const payload = await res.json();
      if (payload && payload.detail) detail = payload.detail;
    } catch {
      /* non-JSON error body */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

const qs = (params = {}) => {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return;
    search.append(key, value);
  });
  const s = search.toString();
  return s ? `?${s}` : '';
};

export const api = {
  // system
  health: (opts) => request('/health', opts),
  thresholds: (opts) => request('/fraud/thresholds', opts),
  scamCategories: (opts) => request('/fraud/scam-categories', opts),
  dashboard: (opts) => request('/dashboard/summary', opts),

  // transactions / fraud
  transactions: (params, opts) => request(`/transactions${qs(params)}`, opts),
  transaction: (id, opts) => request(`/transactions/${id}`, opts),
  transactionRisk: (id, opts) => request(`/transactions/${id}/risk`, opts),
  predictFraud: (payload, opts) =>
    request('/fraud/predict', { ...opts, method: 'POST', body: payload }),

  // borrowers / repayment
  borrowers: (params, opts) => request(`/borrowers${qs(params)}`, opts),
  borrower: (id, opts) => request(`/borrowers/${id}`, opts),
  repaymentRisk: (id, opts) => request(`/borrowers/${id}/repayment-risk`, opts),
  borrowerShap: (id, opts) => request(`/borrowers/${id}/shap`, opts),
  earlyWarnings: (id, opts) => request(`/borrowers/${id}/early-warnings`, opts),
  borrowerTimeline: (id, params, opts) =>
    request(`/borrowers/${id}/timeline${qs(params)}`, opts),

  // loans
  loans: (params, opts) => request(`/loans${qs(params)}`, opts),
  loan: (id, opts) => request(`/loans/${id}`, opts),
  loanUsage: (id, opts) => request(`/loans/${id}/usage`, opts),

  // money-flow graph
  graphAccounts: (opts) => request('/graph/accounts', opts),
  moneyFlow: (params, opts) => request(`/graph/money-flow${qs(params)}`, opts),
  cycles: (opts) => request('/graph/cycles', opts),
  accountTrace: (id, opts) => request(`/graph/account/${id}`, opts),

  // alerts
  alerts: (params, opts) => request(`/alerts${qs(params)}`, opts),
  updateAlert: (id, status, opts) =>
    request(`/alerts/${id}`, { ...opts, method: 'PATCH', body: { status } }),

  // interventions
  interventions: (params, opts) => request(`/interventions${qs(params)}`, opts),
  interventionHistory: (params, opts) =>
    request(`/interventions/history${qs(params)}`, opts),
  recommendations: (subjectType, subjectId, opts) =>
    request(
      `/interventions/recommendations${qs({ subject_type: subjectType, subject_id: subjectId })}`,
      opts,
    ),
  createIntervention: (payload, opts) =>
    request('/interventions', { ...opts, method: 'POST', body: payload }),
  updateIntervention: (id, payload, opts) =>
    request(`/interventions/${id}`, { ...opts, method: 'PATCH', body: payload }),
};

export default api;
