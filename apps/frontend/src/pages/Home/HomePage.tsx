import "./HomePage.css";

const activity = [
  {
    id: "e9af3c71",
    handler: "billing.capture",
    state: "running",
    detail: "worker-04 · 1.2s",
  },
  {
    id: "02d61b4e",
    handler: "email.receipt",
    state: "succeeded",
    detail: "worker-02 · 428ms",
  },
  {
    id: "b51aa879",
    handler: "ledger.reconcile",
    state: "retrying",
    detail: "attempt 2 · in 8s",
  },
] as const;

function RelayMark() {
  return (
    <svg aria-hidden="true" className="relay-mark" viewBox="0 0 32 32">
      <path d="M5 7.5h12.5a6.5 6.5 0 0 1 0 13H13" />
      <path d="m8 16 5-5v10l-5-5Z" />
      <circle cx="24.5" cy="9" r="2.5" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20">
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  );
}

function TrendChart() {
  return (
    <svg
      aria-hidden="true"
      className="trend-chart"
      preserveAspectRatio="none"
      viewBox="0 0 620 190"
    >
      <defs>
        <linearGradient id="area-fill" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#b9ff66" stopOpacity=".25" />
          <stop offset="1" stopColor="#b9ff66" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g className="trend-grid">
        <path d="M0 24H620M0 72H620M0 120H620M0 168H620" />
        <path d="M70 0V190M210 0V190M350 0V190M490 0V190" />
      </g>
      <path
        className="trend-area"
        d="M0 152C32 151 45 139 75 142S122 125 153 130 195 115 228 119 272 88 305 95 345 70 382 82 424 52 458 64 506 37 540 42 585 20 620 29V190H0Z"
      />
      <path
        className="trend-line"
        d="M0 152C32 151 45 139 75 142S122 125 153 130 195 115 228 119 272 88 305 95 345 70 382 82 424 52 458 64 506 37 540 42 585 20 620 29"
      />
      <circle cx="620" cy="29" r="5" />
    </svg>
  );
}

function OperationsPreview() {
  return (
    <section
      aria-label="Illustrative Relay operations preview"
      className="operations-preview"
      id="product-preview"
    >
      <div className="preview-topbar">
        <div className="preview-crumbs">
          <span className="preview-logo">
            <RelayMark />
          </span>
          <span>northwind</span>
          <span className="crumb-separator">/</span>
          <span className="environment-pill">production</span>
        </div>
        <div className="live-status">
          <span className="live-dot" />
          preview
        </div>
      </div>

      <div className="preview-body">
        <div className="preview-heading">
          <div>
            <span className="section-kicker">Last 60 minutes</span>
            <h2>System pulse</h2>
          </div>
          <span className="sample-label">Illustrative data</span>
        </div>

        <div className="metric-grid" id="performance">
          <article>
            <span>Queue depth</span>
            <strong>1,204</strong>
            <small className="metric-warn">+12% today</small>
          </article>
          <article>
            <span>Throughput</span>
            <strong>
              842<span>/min</span>
            </strong>
            <small className="metric-good">Within target</small>
          </article>
          <article>
            <span>p95 dispatch</span>
            <strong>
              86<span>ms</span>
            </strong>
            <small className="metric-good">Under 100ms</small>
          </article>
          <article>
            <span>Workers</span>
            <strong>
              6<span>/6</span>
            </strong>
            <small className="metric-good">All healthy</small>
          </article>
        </div>

        <div className="chart-card">
          <div className="chart-header">
            <span>Jobs processed</span>
            <strong>50.4k</strong>
          </div>
          <TrendChart />
          <div className="chart-axis" aria-hidden="true">
            <span>60m ago</span>
            <span>Now</span>
          </div>
        </div>

        <div className="activity-card">
          <div className="activity-title">
            <span>Recent activity</span>
            <span>State changes stream in here</span>
          </div>
          <div className="activity-list">
            {activity.map((job) => (
              <div className="activity-row" key={job.id}>
                <span className={`state-dot state-${job.state}`} />
                <code>{job.id}</code>
                <strong>{job.handler}</strong>
                <span className={`state-label state-${job.state}`}>
                  {job.state}
                </span>
                <small>{job.detail}</small>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

export function HomePage() {
  return (
    <div className="home-page">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <header className="site-header">
        <a aria-label="Relay home" className="brand" href="#top">
          <RelayMark />
          <span>Relay</span>
          <small>Job infrastructure</small>
        </a>

        <nav aria-label="Primary navigation" className="primary-nav">
          <a href="#product-preview">Product</a>
          <a href="#principles">Principles</a>
          <a href="#performance">Performance</a>
        </nav>

        <a className="header-action" href="#product-preview">
          Explore the console
          <ArrowIcon />
        </a>
      </header>

      <main id="main-content">
        <section className="hero" id="top">
          <div className="hero-glow" aria-hidden="true" />
          <div className="hero-copy">
            <div className="eyebrow">
              <span className="eyebrow-pulse" />
              Self-hosted · failure-ready
            </div>

            <h1>
              Jobs that keep their{" "}
              <span>promises.</span>
            </h1>

            <p className="hero-lede">
              Relay is distributed job infrastructure built for the moment
              things go wrong. Postgres keeps the truth, Redis moves the work,
              and every transition stays visible.
            </p>

            <div className="hero-actions">
              <a className="button button-primary" href="#product-preview">
                See Relay in action
                <ArrowIcon />
              </a>
              <a className="button button-secondary" href="#principles">
                Why it stays correct
              </a>
            </div>

            <div
              aria-label="Relay guarantees"
              className="hero-proof"
              id="principles"
            >
              <div>
                <strong>0</strong>
                <span>job-loss durability target</span>
              </div>
              <div>
                <strong>&lt;25ms</strong>
                <span>p99 enqueue target</span>
              </div>
              <div>
                <strong>5k/s</strong>
                <span>sustained throughput target</span>
              </div>
            </div>
          </div>

          <div className="hero-visual">
            <div className="preview-shadow" aria-hidden="true" />
            <OperationsPreview />
            <div
              className="floating-note floating-note-top"
              aria-hidden="true"
            >
              <span />
              Lease renewed
              <small>worker-04 · 5s ago</small>
            </div>
            <div
              className="floating-note floating-note-bottom"
              aria-hidden="true"
            >
              <span />
              Redis is rebuildable
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
