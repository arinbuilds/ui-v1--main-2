import { useState } from 'react';
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
import { inr, num, titleCase, levelFromCategory } from '../lib/format.js';

export default function Borrowers() {
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [sort, setSort] = useState('score');

  const { data, loading, error, refetch } = useApi(
    () => api.borrowers({ q: search || undefined, sort, limit: 200 }),
    [search, sort],
  );

  const items = data?.items || [];

  return (
    <div className="stack">
      <Card
        title="Borrowers"
        subtitle="Repayment risk from an independent XGBoost model — never derived from the fraud score"
        action={
          <button className="btn ghost sm" onClick={refetch}>
            Refresh
          </button>
        }
      >
        <div className="controls">
          <form
            className="row"
            style={{ gap: 6 }}
            onSubmit={(e) => {
              e.preventDefault();
              setSearch(q.trim());
            }}
          >
            <input
              placeholder="Search name, id or city"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              style={{ width: 250 }}
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
          <select value={sort} onChange={(e) => setSort(e.target.value)}>
            <option value="score">Sort: repayment risk</option>
            <option value="name">Sort: name</option>
            <option value="income">Sort: income</option>
          </select>
          <span className="faint" style={{ fontSize: 12 }}>
            {num(items.length)} shown
          </span>
        </div>
      </Card>

      {error && <ErrorBox error={error} onRetry={refetch} />}
      {loading && !items.length && <Loading />}
      {!loading && !items.length && !error && <Empty label="No borrowers found" />}

      {items.length > 0 && (
        <Card title="Repayment risk ranking">
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Borrower</th>
                  <th>City</th>
                  <th className="right">Income</th>
                  <th className="right">Loans</th>
                  <th className="right">Outstanding</th>
                  <th>Repayment score</th>
                  <th>Band</th>
                  <th>Model</th>
                </tr>
              </thead>
              <tbody>
                {items.map((b) => (
                  <tr key={b.id} className="clickable">
                    <td>
                      <Link to={`/borrowers/${b.id}`} className="strong">
                        {b.name}
                      </Link>
                      <div className="faint" style={{ fontSize: 11 }}>
                        {b.occupation} · {b.employer}
                      </div>
                    </td>
                    <td className="dim">{b.city}</td>
                    <td className="right nowrap">{inr(b.monthly_income, { compact: true })}</td>
                    <td className="right">{b.loans}</td>
                    <td className="right nowrap">{inr(b.outstanding, { compact: true })}</td>
                    <td style={{ minWidth: 150 }}>
                      <ScoreCell value={b.repayment_score} level={levelFromCategory(b.repayment_category)} />
                    </td>
                    <td>
                      <RiskBadge
                        category={b.repayment_category}
                        level={levelFromCategory(b.repayment_category)}
                      />
                    </td>
                    <td>
                      <ModelBadge modelUsed={b.model_used} status={b.prediction_status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Note>
            Repayment bands use the same centralized 0–100 scale as fraud, but the two scores come
            from separate models and are never combined.
          </Note>
        </Card>
      )}
    </div>
  );
}
