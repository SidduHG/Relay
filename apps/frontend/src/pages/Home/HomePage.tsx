import "./HomePage.css";
import { HomeProofSections } from "./HomeProofSections";

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

function RelayMark({ className = "" }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={`relay-mark ${className}`}
      viewBox="0 0 32 32"
    >
      <path d="M5 7.5h12.5a6.5 6.5 0 0 1 0 13H13" />
      <path d="m8 16 5-5v10l-5-5Z" />
      <circle cx="24.5" cy="9" r="2.5" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg
      aria-hidden="true"
      className="h-4 w-4 fill-none stroke-current stroke-[1.7] [stroke-linecap:round] [stroke-linejoin:round]"
      viewBox="0 0 20 20"
    >
      <path d="M4 10h12M11 5l5 5-5 5" />
    </svg>
  );
}

function TrendChart() {
  return (
    <svg
      aria-hidden="true"
      className="trend-chart mt-2 h-[clamp(90px,10vw,145px)] w-full overflow-visible"
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
      className="operations-preview relative overflow-hidden rounded-[13px] border border-white/15 bg-[rgba(18,21,18,0.96)] shadow-[0_38px_90px_rgba(0,0,0,0.4)] [transform:rotateY(-2deg)_rotateX(1deg)] max-[760px]:transform-none"
      id="product-preview"
    >
      <div className="flex h-[54px] items-center justify-between border-b border-relay-line px-[18px]">
        <div className="flex items-center gap-2 text-[0.72rem] font-semibold text-[#cbd0c7]">
          <span className="grid h-[26px] w-[26px] place-items-center rounded-md border border-relay-acid/20 bg-relay-acid/[0.08]">
            <RelayMark className="h-[17px] w-[17px]" />
          </span>
          <span className="max-[430px]:hidden">northwind</span>
          <span className="text-[#50564f] max-[430px]:hidden">/</span>
          <span className="rounded border border-relay-line bg-white/[0.04] px-[7px] py-1 font-mono text-[0.61rem] text-[#9ca199]">
            production
          </span>
        </div>
        <div className="flex items-center gap-[7px] font-mono text-[0.63rem] uppercase tracking-[0.06em] text-[#8e958b]">
          <span className="live-dot h-1.5 w-1.5 rounded-full bg-relay-acid shadow-[0_0_10px_rgba(185,255,102,0.7)]" />
          preview
        </div>
      </div>

      <div className="p-[clamp(18px,2.5vw,30px)]">
        <div className="flex items-center justify-between">
          <div>
            <span className="mb-[5px] block font-mono text-[0.58rem] uppercase tracking-[0.09em] text-[#737a71]">
              Last 60 minutes
            </span>
            <h2 className="m-0 text-[1.03rem] font-semibold tracking-[-0.02em] text-[#e9ebe4]">
              System pulse
            </h2>
          </div>
          <span className="rounded border border-relay-line px-[7px] py-1 font-mono text-[0.53rem] uppercase tracking-[0.08em] text-[#70766e] max-[430px]:hidden">
            Illustrative data
          </span>
        </div>

        <div
          className="metric-grid mt-5 grid grid-cols-4 rounded-[7px] border border-relay-line max-[760px]:grid-cols-2"
          id="performance"
        >
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

        <div className="mt-[13px] rounded-[7px] border border-relay-line bg-[#0f120f] px-[15px] pb-[10px] pt-[15px]">
          <div className="flex items-center justify-between text-[0.61rem] text-[#7d847a]">
            <span>Jobs processed</span>
            <strong className="font-mono text-[0.72rem] font-medium text-[#daddd4]">
              50.4k
            </strong>
          </div>
          <TrendChart />
          <div
            aria-hidden="true"
            className="flex justify-between font-mono text-[0.51rem] text-[#50564f]"
          >
            <span>60m ago</span>
            <span>Now</span>
          </div>
        </div>

        <div className="mt-[13px] rounded-[7px] border border-relay-line">
          <div className="flex min-h-[38px] items-center justify-between border-b border-relay-line px-[13px] text-[0.61rem] text-[#9aa097]">
            <span>Recent activity</span>
            <span className="font-mono text-[0.51rem] text-[#565c54] max-[430px]:hidden">
              State changes stream in here
            </span>
          </div>
          <div>
            {activity.map((job) => (
              <div
                className="activity-row grid min-h-[34px] grid-cols-[8px_68px_minmax(120px,1fr)_58px_100px] items-center gap-[9px] px-[13px] text-[0.56rem] text-[#858c82] max-[760px]:grid-cols-[8px_minmax(110px,1fr)_58px]"
                key={job.id}
              >
                <span className={`state-dot state-${job.state}`} />
                <code className="font-mono text-[#666d64] max-[760px]:hidden">
                  {job.id}
                </code>
                <strong className="overflow-hidden text-ellipsis whitespace-nowrap font-medium text-[#c3c8bf]">
                  {job.handler}
                </strong>
                <span className={`state-label state-${job.state}`}>
                  {job.state}
                </span>
                <small className="justify-self-end text-[#646a62] max-[760px]:hidden">
                  {job.detail}
                </small>
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
    <div className="home-page relative min-h-screen overflow-hidden bg-relay-ink text-relay-paper">
      <a
        className="skip-link fixed left-3 top-3 z-[100] rounded-md bg-relay-acid px-[14px] py-[10px] text-[0.82rem] font-bold text-relay-ink"
        href="#main-content"
      >
        Skip to content
      </a>

      <header className="relative z-10 mx-auto grid h-[82px] w-[min(1440px,calc(100%_-_64px))] grid-cols-[1fr_auto_1fr] items-center border-b border-relay-line max-[760px]:h-[70px] max-[760px]:w-[calc(100%_-_32px)] max-[760px]:grid-cols-[1fr_auto]">
        <a
          aria-label="Relay home"
          className="inline-flex w-fit items-center gap-2.5 justify-self-start text-relay-paper no-underline"
          href="#top"
        >
          <RelayMark className="h-[27px] w-[27px]" />
          <span className="font-display text-[1.45rem] tracking-[-0.04em]">
            Relay
          </span>
          <small className="border-l border-relay-line-strong pl-[11px] font-mono text-[0.63rem] uppercase tracking-[0.08em] text-[#777d75] max-[760px]:hidden">
            Job infrastructure
          </small>
        </a>

        <nav
          aria-label="Primary navigation"
          className="flex items-center gap-[34px] max-[1120px]:gap-[22px] max-[760px]:hidden [&>a]:relative [&>a]:py-2.5 [&>a]:text-[0.76rem] [&>a]:font-semibold [&>a]:uppercase [&>a]:tracking-[0.05em] [&>a]:text-relay-muted [&>a]:no-underline [&>a]:transition-colors [&>a:hover]:text-relay-paper"
        >
          <a href="#features">Product</a>
          <a href="#questions">Principles</a>
          <a href="#performance">Performance</a>
        </nav>

        <a
          className="inline-flex items-center gap-[9px] justify-self-end rounded-full border border-relay-line-strong px-[15px] py-2.5 text-[0.78rem] font-semibold text-relay-paper no-underline transition-colors hover:border-relay-acid/50 hover:bg-white/[0.05] max-[760px]:px-3"
          href="#product-preview"
        >
          Explore the console
          <span className="max-[430px]:hidden">
            <ArrowIcon />
          </span>
        </a>
      </header>

      <main id="main-content">
        <section
          className="relative z-[1] mx-auto grid min-h-[calc(100vh-82px)] w-[min(1320px,calc(100%_-_96px))] grid-cols-[minmax(0,0.83fr)_minmax(540px,1.17fr)] items-center gap-[clamp(48px,6vw,110px)] py-[72px] pb-[88px] max-[1120px]:w-[min(820px,calc(100%_-_64px))] max-[1120px]:grid-cols-1 max-[1120px]:pt-[82px] max-[760px]:min-h-0 max-[760px]:w-[calc(100%_-_34px)] max-[760px]:py-16 max-[760px]:pb-[76px]"
          id="top"
        >
          <div className="hero-glow pointer-events-none absolute left-[-28%] top-1/4 h-[430px] w-[430px] rounded-full bg-relay-coral/[0.09] blur-[100px]" aria-hidden="true" />
          <div className="relative z-[3] max-[1120px]:max-w-[720px]">
            <div className="mb-[26px] inline-flex items-center gap-2.5 font-mono text-[0.68rem] uppercase tracking-[0.1em] text-[#b3b8b0] max-[430px]:mb-5 max-[430px]:text-[0.6rem]">
              <span className="h-[7px] w-[7px] rounded-full bg-relay-acid shadow-[0_0_0_4px_rgba(185,255,102,0.09)]" />
              Self-hosted · failure-ready
            </div>

            <h1 className="m-0 max-w-[720px] font-display text-[clamp(4.2rem,6.3vw,7rem)] font-normal leading-[0.88] tracking-[-0.068em] text-relay-paper max-[1120px]:text-[clamp(4.5rem,11vw,7rem)] max-[760px]:text-[clamp(3.55rem,18vw,5.4rem)]">
              Jobs that keep their{" "}
              <span className="block text-transparent [-webkit-text-stroke:1px_rgba(244,243,236,0.58)]">
                promises.
              </span>
            </h1>

            <p className="mt-8 max-w-[610px] text-[clamp(1rem,1.25vw,1.15rem)] leading-[1.72] text-[#a9afa6] max-[760px]:text-[0.98rem]">
              Relay is distributed job infrastructure built for the moment
              things go wrong. Postgres keeps the truth, Redis moves the work,
              and every transition stays visible.
            </p>

            <div className="mt-[34px] flex flex-wrap gap-3 max-[430px]:w-full">
              <a
                className="inline-flex min-h-[49px] items-center justify-center gap-[18px] rounded-[7px] border border-relay-acid bg-relay-acid px-5 text-[0.84rem] font-bold text-[#11150f] no-underline shadow-[0_12px_32px_rgba(185,255,102,0.12)] transition hover:-translate-y-0.5 hover:bg-[#cbff8c] max-[430px]:w-full"
                href="#product-preview"
              >
                See Relay in action
                <ArrowIcon />
              </a>
              <a
                className="inline-flex min-h-[49px] items-center justify-center rounded-[7px] border border-relay-line-strong bg-white/[0.025] px-5 text-[0.84rem] font-bold text-relay-paper no-underline transition hover:-translate-y-0.5 hover:border-white/30 hover:bg-white/[0.06] max-[430px]:w-full"
                href="#questions"
              >
                Why it stays correct
              </a>
            </div>

            <div
              aria-label="Relay guarantees"
              className="mt-[54px] grid max-w-[560px] grid-cols-3 border-t border-relay-line max-[760px]:mt-[42px] max-[430px]:grid-cols-1 [&>div]:grid [&>div]:gap-1.5 [&>div]:px-[18px] [&>div]:pt-[18px] [&>div:first-child]:pl-0 [&>div+div]:border-l [&>div+div]:border-relay-line max-[430px]:[&>div]:grid-cols-[82px_1fr] max-[430px]:[&>div]:items-center max-[430px]:[&>div]:border-b max-[430px]:[&>div]:border-l-0 max-[430px]:[&>div]:border-relay-line max-[430px]:[&>div]:px-0 max-[430px]:[&>div]:py-[13px] [&_strong]:font-mono [&_strong]:text-[1.05rem] [&_strong]:font-medium [&_strong]:text-relay-paper [&_span]:text-[0.7rem] [&_span]:leading-[1.4] [&_span]:text-[#777d75] max-[430px]:[&_span]:text-[0.69rem]"
              id="principles"
            >
              <div><strong>0</strong><span>job-loss durability target</span></div>
              <div><strong>&lt;25ms</strong><span>p99 enqueue target</span></div>
              <div><strong>5k/s</strong><span>sustained throughput target</span></div>
            </div>
          </div>

          <div className="relative z-[2] min-w-0 [perspective:1200px] max-[1120px]:mt-4">
            <div className="absolute inset-x-[4%] bottom-[-5%] h-[30%] translate-z-[-20px] bg-black opacity-70 blur-[42px]" aria-hidden="true" />
            <OperationsPreview />
            <div
              className="floating-note floating-note-top absolute right-[-29px] top-[21%] z-[8] grid grid-cols-[8px_auto] items-center gap-x-[9px] gap-y-0.5 rounded-[7px] border border-white/15 bg-[rgba(24,28,23,0.92)] px-3 py-2.5 text-[0.62rem] text-[#cfd3ca] shadow-[0_14px_34px_rgba(0,0,0,0.34)] backdrop-blur-xl max-[760px]:right-[-8px] max-[760px]:top-[-20px] max-[430px]:hidden"
              aria-hidden="true"
            >
              <span />
              Lease renewed
              <small className="font-mono text-[0.49rem] text-[#686f65]">worker-04 · 5s ago</small>
            </div>
            <div
              className="floating-note floating-note-bottom absolute bottom-[-18px] left-[12%] z-[8] grid grid-cols-[8px_auto] items-center gap-x-[9px] gap-y-0.5 rounded-[7px] border border-white/15 bg-[rgba(24,28,23,0.92)] px-3 py-2.5 text-[0.62rem] text-[#cfd3ca] shadow-[0_14px_34px_rgba(0,0,0,0.34)] backdrop-blur-xl max-[760px]:left-3 max-[430px]:hidden"
              aria-hidden="true"
            >
              <span />
              Redis is rebuildable
            </div>
          </div>
        </section>
        <HomeProofSections />
      </main>
    </div>
  );
}
