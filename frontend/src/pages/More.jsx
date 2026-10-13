import { Link } from 'react-router-dom';
import Icon from '../components/Icons.jsx';

const tools = [
  { title: 'Risk overview', description: 'Transactions, fraud signals and repayment trends', icon: 'chart', to: '/dashboard' },
  { title: 'Money-flow graph', description: 'Explore links between accounts', icon: 'activity', to: '/graph' },
  { title: 'Alert queue', description: 'Review items that need attention', icon: 'bell', to: '/alerts' },
  { title: 'Interventions', description: 'Review recommended actions and history', icon: 'shield', to: '/interventions' },
  { title: 'Model health', description: 'Check model status and thresholds', icon: 'chart', to: '/models' },
];

export default function More() {
  return (
    <div className="more-page">
      <div className="more-intro">
        <span className="more-badge"><Icon name="more" size={16} /> FINTECHSICO</span>
        <h2>More tools</h2>
        <p>Explore account activity and financial risk tools.</p>
      </div>
      <div className="more-links">
        {tools.map((tool) => (
          <Link className="more-link" to={tool.to} key={tool.to}>
            <span className="more-link-icon"><Icon name={tool.icon} size={22} /></span>
            <span className="more-link-copy"><strong>{tool.title}</strong><small>{tool.description}</small></span>
            <Icon name="arrow" size={18} />
          </Link>
        ))}
      </div>
    </div>
  );
}
