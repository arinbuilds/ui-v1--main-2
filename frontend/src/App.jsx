import { Routes, Route, Navigate } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import Home from './pages/Home.jsx';
import Dashboard from './pages/Dashboard.jsx';
import Transactions from './pages/Transactions.jsx';
import TransactionDetail from './pages/TransactionDetail.jsx';
import Borrowers from './pages/Borrowers.jsx';
import BorrowerDetail from './pages/BorrowerDetail.jsx';
import MoneyFlow from './pages/MoneyFlow.jsx';
import Alerts from './pages/Alerts.jsx';
import Interventions from './pages/Interventions.jsx';
import ModelHealth from './pages/ModelHealth.jsx';
import More from './pages/More.jsx';

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/transactions" element={<Transactions />} />
        <Route path="/transactions/:id" element={<TransactionDetail />} />
        <Route path="/borrowers" element={<Borrowers />} />
        <Route path="/borrowers/:id" element={<BorrowerDetail />} />
        <Route path="/graph" element={<MoneyFlow />} />
        <Route path="/alerts" element={<Alerts />} />
        <Route path="/interventions" element={<Interventions />} />
        <Route path="/models" element={<ModelHealth />} />
        <Route path="/more" element={<More />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
