import { useContext } from 'react';
import { Link } from 'react-router-dom';
import Icon from '../components/Icons.jsx';
import { AppActionContext } from '../components/Layout.jsx';

const sendActions = [
  { title: 'Scan & Pay', icon: 'scan', action: 'scan' },
  { title: 'To Mobile', icon: 'mobile', action: 'mobile' },
  { title: 'To Self', icon: 'person', action: 'self' },
  { title: 'To Bank A/c', icon: 'bank', action: 'bank' },
];

const savingsTools = [
  { title: 'Expenses', icon: 'receipt', to: '/transactions' },
  { title: 'Savings goals', icon: 'piggy', to: '/dashboard' },
  { title: 'Statistics', icon: 'chart', to: '/dashboard' },
];

const accountTools = [
  { title: 'Transaction history', icon: 'receipt', to: '/transactions' },
  { title: 'Borrower accounts', icon: 'bank', to: '/borrowers' },
  { title: 'Payment activity', icon: 'wallet', to: '/transactions' },
  { title: 'Safety alerts', icon: 'shield', to: '/alerts' },
];

function CardHeading({ title, subtitle, to, action = 'View all' }) {
  return (
    <div className="home-card-heading">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {to && <Link to={to} className="home-card-link">{action}<Icon name="arrow" size={16} /></Link>}
    </div>
  );
}

export default function Home() {
  const { openScan, openPayment } = useContext(AppActionContext);

  return (
    <div className="home-screen">
      <section className="save-hero">
        <div className="hero-copy">
          <span className="hero-kicker">A little more control, every day</span>
          <h1>Make room for your next goal.</h1>
          <p>Keep spending, saving and account activity together in one simple view.</p>
          <Link className="hero-button" to="/dashboard">
            Explore insights <Icon name="arrow" size={17} />
          </Link>
        </div>
        <div className="hero-art" aria-hidden="true">
          <span className="hero-rupee">₹</span>
          <div className="piggy-illustration"><Icon name="piggy" size={86} strokeWidth={1.4} /></div>
          <span className="hero-spark spark-one">✦</span>
          <span className="hero-spark spark-two">✦</span>
        </div>
      </section>

      <div className="home-feed">
        <section className="home-card send-card">
          <CardHeading title="Send Money" subtitle="From your bank account or wallet" to="/transactions" action="Recent" />
          <div className="send-actions">
            {sendActions.map((item) => (
              <button
                className="send-action"
                key={item.title}
                type="button"
                onClick={() => item.action === 'scan' ? openScan() : openPayment(item.title)}
              >
                <span className="action-icon"><Icon name={item.icon} size={27} /></span>
                <span>{item.title}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="home-card savings-card">
          <CardHeading title={<>FintechSico Save <span className="title-emoji">✦</span></>} subtitle="Smarter ways to understand and plan your money" />
          <div className="savings-tools">
            {savingsTools.map((item) => (
              <Link className="home-tool" to={item.to} key={item.title}>
                <span className={`tool-icon ${item.icon}`}><Icon name={item.icon} size={27} /></span>
                <span>{item.title}</span>
              </Link>
            ))}
          </div>
        </section>

        <section className="home-card accounts-card">
          <CardHeading title="My Accounts" subtitle="Your accounts and payment activity" to="/more" action="Manage" />
          <div className="account-tools">
            {accountTools.map((item) => (
              <Link className="account-tool" to={item.to} key={item.title}>
                <span className="account-icon"><Icon name={item.icon} size={26} /></span>
                <span>{item.title}</span>
              </Link>
            ))}
          </div>
          <div className="account-card-footer">
            <span className="account-avatar"><Icon name="bank" size={16} /></span>
            <span><strong>Account activity</strong><small>Transactions, accounts and alerts</small></span>
            <Link to="/transactions" aria-label="View account activity"><Icon name="arrow" size={19} /></Link>
          </div>
        </section>

        <Link className="home-promo" to="/alerts">
          <span className="promo-icon"><Icon name="shield" size={25} /></span>
          <span className="promo-copy"><strong>Stay in control of every payment</strong><small>Review activity and get to important alerts quickly.</small></span>
          <Icon name="arrow" size={20} />
        </Link>

        <p className="home-demo-note">Payment screens are a prototype preview. No money is moved.</p>
      </div>
    </div>
  );
}
