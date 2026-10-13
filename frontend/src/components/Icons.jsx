const paths = {
  search: <><circle cx="11" cy="11" r="6.5" /><path d="m16 16 4.5 4.5" /></>,
  message: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-5 4v-4.8A2.5 2.5 0 0 1 4 13.5z" /><path d="M8 8h8M8 11h5" /></>,
  scan: <><path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" /><path d="M8 8h3v3H8zM14 8h2v2h-2zM14 14h3v3h-3zM8 14h2v3H8z" /></>,
  mobile: <><rect x="7" y="2.5" width="10" height="19" rx="2.2" /><path d="M10 5h4M11 18.5h2" /><path d="m4 9-2 2 2 2M20 9l2 2-2 2" /></>,
  person: <><circle cx="12" cy="7" r="3.5" /><path d="M5 21v-1.5a7 7 0 0 1 14 0V21" /><path d="m3 13 2 2 3-3" /></>,
  bank: <><path d="m3 9 9-6 9 6M4 10h16M5 20h14M3 22h18" /><path d="M7 10v9M12 10v9M17 10v9" /></>,
  receipt: <><path d="M6 3h12v18l-3-2-3 2-3-2-3 2z" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  piggy: <><path d="M5 11a6.5 6.5 0 0 1 6.5-5h2a6.5 6.5 0 0 1 6.1 4.2H22v4h-2.1a6.5 6.5 0 0 1-5.9 3.8h-4l-2.5 2H6v-3.3a6.5 6.5 0 0 1-1-5.7Z" /><path d="M10 6V4h5M16 10h.01M8 18v3M4 12H2" /></>,
  chart: <><path d="M4 19V5M4 19h17" /><path d="m7 15 4-4 3 2 5-6" /><path d="M16 7h3v3" /></>,
  wallet: <><path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H20v16H6.5A2.5 2.5 0 0 1 4 17.5z" /><path d="M4 7h13a2 2 0 0 1 2 2v2h-5a2 2 0 0 0 0 4h5v2" /><path d="M14 13h.01" /></>,
  card: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18M7 15h4" /></>,
  home: <><path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7h-6v7H4a1 1 0 0 1-1-1z" /></>,
  activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
  more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
  arrow: <><path d="M5 12h14M13 6l6 6-6 6" /></>,
  bell: <><path d="M18 9a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
  shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" /><path d="m9 12 2 2 4-4" /></>,
};

export default function Icon({ name, size = 22, strokeWidth = 1.8, className = '' }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name] || paths.activity}
    </svg>
  );
}
