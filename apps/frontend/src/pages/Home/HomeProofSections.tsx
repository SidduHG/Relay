import type { CSSProperties, ReactNode } from "react";
import "./HomeProofSections.css";

const questions = [
  {
    number: "01",
    question: "Is anything on fire right now?",
    answer:
      "See dead jobs, silent workers, and queues growing beyond capacity in one focused incident view.",
  },
  {
    number: "02",
    question: "Why did this job fail?",
    answer:
      "Follow its full lifecycle, every attempt, the stack trace, and the exact payload that ran.",
  },
  {
    number: "03",
    question: "Is the queue keeping up?",
    answer:
      "Compare depth, throughput, and tail latency by queue and handler over the same time window.",
  },
  {
    number: "04",
    question: "Which worker is misbehaving?",
    answer:
      "Inspect heartbeat age, concurrency in use, active jobs, and every lease a stale worker released.",
  },
] as const;

type FeatureRowProps = {
  body: string;
  eyebrow: string;
  points: readonly string[];
  reverse?: boolean;
  title: string;
  visual: ReactNode;
};

function CheckMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 20 20">
      <path d="m4 10.5 3.5 3.5L16 5.5" />
    </svg>
  );
}

function FeatureRow({
  body,
  eyebrow,
  points,
  reverse = false,
  title,
  visual,
}: FeatureRowProps) {
  const desktopColumns = reverse
    ? "min-[1041px]:grid-cols-[minmax(500px,1.24fr)_minmax(300px,0.76fr)] min-[1041px]:[&>.feature-copy]:order-2 min-[1041px]:[&>.feature-visual]:order-1"
    : "min-[1041px]:grid-cols-[minmax(300px,0.76fr)_minmax(500px,1.24fr)]";

  return (
    <article
      className={`feature-row grid grid-cols-1 items-center gap-12 border-t border-relay-line py-[76px] min-[761px]:gap-[clamp(54px,8vw,120px)] min-[761px]:py-[clamp(80px,10vw,132px)] min-[1041px]:min-h-[650px] ${desktopColumns}`}
    >
      <div className="feature-copy max-w-[650px] min-[1041px]:max-w-none">
        <span className="proof-eyebrow text-relay-acid">{eyebrow}</span>
        <h3 className="mt-6 font-display text-[clamp(2.45rem,12vw,3.4rem)] font-normal leading-[0.99] tracking-[-0.057em] min-[761px]:text-[clamp(2.55rem,4vw,4.25rem)]">
          {title}
        </h3>
        <p className="mt-[27px] text-[0.98rem] leading-[1.72] text-[#999f96]">
          {body}
        </p>
        <ul className="mt-[30px] grid list-none gap-[15px] p-0">
          {points.map((point) => (
            <li
              className="grid grid-cols-[20px_1fr] gap-[11px] text-[0.81rem] leading-[1.52] text-[#c0c5bb]"
              key={point}
            >
              <span className="check-mark mt-px grid h-[18px] w-[18px] place-items-center rounded-full border border-relay-acid/20 bg-relay-acid/[0.07] text-relay-acid">
                <CheckMark />
              </span>
              {point}
            </li>
          ))}
        </ul>
      </div>
      <div className="feature-visual min-w-0">{visual}</div>
    </article>
  );
}

const laneTicks = [
  ["success", "running", "success", "success", "running", "queued", "success", "running", "success"],
  ["success", "queued", "running", "success", "success", "queued", "running", "queued", "success", "queued", "success"],
  ["queued", "success", "queued", "running", "queued", "queued", "success", "queued", "running", "queued", "queued", "success", "queued"],
  ["queued", "queued", "delayed", "queued", "queued", "delayed", "queued", "queued", "queued", "delayed", "queued", "queued", "queued", "queued"],
] as const;

function LaneTapeVisual() {
  const lanes = ["critical", "high", "normal", "low"];

  return (
    <div
      aria-label="Interface concept showing jobs moving through four priority lanes"
      className="proof-panel lane-panel"
      role="img"
    >
      <div className="panel-bar">
        <span>Priority lanes</span>
        <small>last 90 seconds</small>
      </div>
      <div className="lane-summary">
        <span>Dispatch velocity</span>
        <strong>842 <small>jobs/min</small></strong>
        <span className="healthy-label">Healthy</span>
      </div>
      <div className="lane-list">
        {lanes.map((lane, laneIndex) => (
          <div className="lane-row" key={lane}>
            <div className="lane-name">
              <span className={`lane-dot lane-${lane}`} />
              {lane}
            </div>
            <div className="lane-track">
              {laneTicks[laneIndex].map((state, index) => (
                <i
                  className={`job-tick tick-${state}`}
                  key={`${lane}-${index}`}
                  style={{ "--tick-index": index } as CSSProperties}
                />
              ))}
            </div>
            <span className="lane-count">{[18, 43, 126, 207][laneIndex]}</span>
          </div>
        ))}
      </div>
      <div className="lane-legend">
        <span><i className="tick-running" /> running</span>
        <span><i className="tick-success" /> succeeded</span>
        <span><i className="tick-queued" /> queued</span>
        <strong>Low lane aging in 01:42</strong>
      </div>
    </div>
  );
}

const errorClusters = [
  {
    count: "428",
    handler: "billing.capture",
    message: "ConnectionTimeout: ledger-api",
    tone: "danger",
  },
  {
    count: "184",
    handler: "email.receipt",
    message: "SMTP 421: service unavailable",
    tone: "warning",
  },
  {
    count: "61",
    handler: "media.thumbnail",
    message: "Unknown handler on worker pool",
    tone: "violet",
  },
] as const;

function DlqVisual() {
  return (
    <div
      aria-label="Interface concept grouping dead-letter jobs by error signature"
      className="proof-panel dlq-panel"
      role="img"
    >
      <div className="panel-bar">
        <span>Error clusters</span>
        <small>673 dead jobs · 3 causes</small>
      </div>
      <div className="cluster-list">
        {errorClusters.map((cluster) => (
          <div className="cluster-row" key={cluster.handler}>
            <span className={`cluster-count cluster-${cluster.tone}`}>
              {cluster.count}
            </span>
            <div>
              <strong>{cluster.message}</strong>
              <small>{cluster.handler} · last seen 18s ago</small>
            </div>
            <span className="cluster-action">Replay</span>
          </div>
        ))}
      </div>
      <div className="cluster-footer">
        <span><i /> 82% of failures share one root cause</span>
        <span className="cluster-action cluster-action-primary">Replay selected</span>
      </div>
    </div>
  );
}

function ControlsVisual() {
  return (
    <div
      aria-label="Interface concept showing queue rate limits, priority usage, and a schedule"
      className="proof-panel controls-panel"
      role="img"
    >
      <div className="panel-bar">
        <span>Queue controls</span>
        <small>payments</small>
      </div>
      <div className="control-grid">
        <div className="control-card rate-card">
          <span>Rate limit</span>
          <strong>84 <small>/ 120 sec</small></strong>
          <div className="usage-bar"><i /></div>
          <small>70% utilised</small>
        </div>
        <div className="control-card concurrency-card">
          <span>Concurrency</span>
          <strong>18 <small>/ 24 slots</small></strong>
          <div className="slot-grid">
            {Array.from({ length: 24 }, (_, index) => (
              <i className={index < 18 ? "slot-active" : ""} key={index} />
            ))}
          </div>
        </div>
      </div>
      <div className="priority-mix">
        <div>
          <span>Priority mix</span>
          <small>critical 8% · high 24% · normal 52% · low 16%</small>
        </div>
        <div className="priority-bar">
          <i className="priority-critical" />
          <i className="priority-high" />
          <i className="priority-normal" />
          <i className="priority-low" />
        </div>
      </div>
      <div className="schedule-row">
        <span className="schedule-icon">↻</span>
        <div>
          <strong>ledger-nightly</strong>
          <small>0 2 * * * · Asia/Kolkata</small>
        </div>
        <span className="schedule-next">next in 04:18:12</span>
        <span className="toggle-on"><i /></span>
      </div>
    </div>
  );
}

function RecoveryVisual() {
  return (
    <div
      aria-label="Diagram concept showing a worker lease expiring and the reaper safely recovering its job"
      className="proof-panel recovery-panel"
      role="img"
    >
      <div className="panel-bar">
        <span>Failure recovery</span>
        <small>job e9af3c71</small>
      </div>
      <div className="recovery-flow">
        <div className="recovery-node">
          <span className="node-icon node-worker">W</span>
          <strong>worker-04</strong>
          <small>heartbeat lost</small>
        </div>
        <span className="flow-link flow-link-failed"><i /></span>
        <div className="recovery-node">
          <span className="node-icon node-lease">L</span>
          <strong>lease</strong>
          <small>expired at 14:02:19</small>
        </div>
        <span className="flow-link flow-link-good"><i /></span>
        <div className="recovery-node">
          <span className="node-icon node-reaper">R</span>
          <strong>reaper</strong>
          <small>requeued safely</small>
        </div>
      </div>
      <div className="recovery-events">
        <div><span>14:01:14</span><i className="event-good" /><strong>Lease extended</strong><small>Postgres deadline +60s</small></div>
        <div><span>14:02:19</span><i className="event-bad" /><strong>Worker became stale</strong><small>no heartbeat for 10s</small></div>
        <div><span>14:02:20</span><i className="event-good" /><strong>Job returned to queue</strong><small>reclaim 1 of 3</small></div>
      </div>
      <div className="truth-strip">
        <span>Postgres</span>
        <strong>source of truth intact</strong>
        <span className="verified-mark">✓ verified</span>
      </div>
    </div>
  );
}

function DependencyVisual() {
  return (
    <div
      aria-label="Dependency graph concept showing fan-out and fan-in jobs"
      className="proof-panel dependency-panel"
      role="img"
    >
      <div className="panel-bar">
        <span>Dependency graph</span>
        <small>release-pipeline · 7 jobs</small>
      </div>
      <div className="dag-canvas">
        <svg aria-hidden="true" preserveAspectRatio="none" viewBox="0 0 600 270">
          <path d="M93 135C145 135 145 55 205 55M93 135H205M93 135C145 135 145 215 205 215" />
          <path d="M285 55C345 55 345 95 395 95M285 135H395M285 215C345 215 345 175 395 175" />
          <path d="M475 95C525 95 515 135 555 135M475 175C525 175 515 135 555 135" />
        </svg>
        <div className="dag-node dag-root"><i /> ingest<small>succeeded</small></div>
        <div className="dag-node dag-a"><i /> validate<small>succeeded</small></div>
        <div className="dag-node dag-b"><i /> compile<small>running</small></div>
        <div className="dag-node dag-c"><i /> assets<small>succeeded</small></div>
        <div className="dag-node dag-d"><i /> unit-test<small>queued</small></div>
        <div className="dag-node dag-e"><i /> scan<small>queued</small></div>
        <div className="dag-node dag-end"><i /> deploy<small>blocked · 2 parents</small></div>
      </div>
      <div className="dag-status">
        <span>3 succeeded</span><span>1 running</span><span>2 queued</span><span>1 blocked</span>
      </div>
    </div>
  );
}

const traceSpans = [
  { label: "POST /v1/jobs", service: "api", start: 0, width: 18, tone: "api", time: "21ms" },
  { label: "postgres.commit", service: "db", start: 8, width: 24, tone: "db", time: "18ms" },
  { label: "queue.wait", service: "redis stream", start: 17, width: 45, tone: "wait", time: "1.18s" },
  { label: "billing.capture", service: "worker-04", start: 59, width: 35, tone: "worker", time: "842ms" },
] as const;

function TraceVisual() {
  return (
    <div
      aria-label="Trace waterfall concept spanning API, database, queue wait, and worker execution"
      className="proof-panel trace-panel"
      role="img"
    >
      <div className="panel-bar">
        <span>Distributed trace</span>
        <small>2.04s total · 4 spans</small>
      </div>
      <div className="trace-id">
        <span>trace</span>
        <code>4bf92f3577b34da6a3ce929d0e0e4736</code>
        <strong>complete</strong>
      </div>
      <div className="trace-axis"><span>0ms</span><span>500ms</span><span>1s</span><span>1.5s</span><span>2s</span></div>
      <div className="trace-list">
        {traceSpans.map((span) => (
          <div className="trace-row" key={span.label}>
            <div className="trace-name"><strong>{span.label}</strong><small>{span.service}</small></div>
            <div className="trace-track">
              <i
                className={`trace-span trace-${span.tone}`}
                style={{ "--span-start": `${span.start}%`, "--span-width": `${span.width}%` } as CSSProperties}
              >
                <span>{span.time}</span>
              </i>
            </div>
          </div>
        ))}
      </div>
      <div className="trace-insight">
        <span>Queue wait is visible</span>
        <strong>58% of total duration</strong>
      </div>
    </div>
  );
}

export function HomeProofSections() {
  return (
    <>
      <section
        className="questions-section relative z-[2] py-[clamp(96px,11vw,160px)] text-[#151813] max-[760px]:py-[88px]"
        id="questions"
      >
        <div className="mx-auto w-[min(1240px,calc(100%_-_96px))] max-[760px]:w-[calc(100%_-_34px)]">
          <div className="max-w-[760px]">
            <span className="proof-eyebrow text-[#72786e]">The 2am problem</span>
            <h2 className="mt-[22px] font-display text-[clamp(3rem,5.6vw,5.8rem)] font-normal leading-[0.96] tracking-[-0.062em] max-[760px]:text-[clamp(2.9rem,14vw,4.2rem)]">
              Answers before the incident channel gets loud.
            </h2>
            <p className="mt-[27px] max-w-[610px] text-[clamp(1rem,1.3vw,1.12rem)] leading-[1.72] text-[#62685f]">
              A queue dashboard should shorten the path from alarm to cause.
              Relay organizes operational truth around the questions people ask
              under pressure.
            </p>
          </div>
          <div className="mt-[clamp(58px,7vw,92px)] grid grid-cols-2 border-l border-t border-[#13171238] max-[760px]:mt-[54px] max-[760px]:grid-cols-1">
            {questions.map((item) => (
              <article
                className="question-card group relative min-h-[270px] overflow-hidden border-b border-r border-[#13171238] p-[clamp(28px,4vw,48px)] transition-colors duration-200 hover:bg-[#121511] hover:text-relay-paper max-[760px]:min-h-[245px] max-[760px]:p-7"
                key={item.number}
              >
                <span className="font-mono text-[0.68rem] tracking-[0.08em] text-[#848a80]">
                  {item.number}
                </span>
                <h3 className="mt-12 max-w-[430px] font-display text-[clamp(1.65rem,2.8vw,2.45rem)] font-normal leading-[1.06] tracking-[-0.045em] max-[760px]:mt-[42px]">
                  {item.question}
                </h3>
                <p className="mt-[17px] max-w-[470px] text-[0.9rem] leading-[1.62] text-[#666c63] transition-colors duration-200 group-hover:text-[#aeb4aa]">
                  {item.answer}
                </p>
                <i
                  aria-hidden="true"
                  className="absolute right-[38px] top-[34px] grid h-9 w-9 place-items-center rounded-full border border-[#13171233] not-italic text-[#686e65] transition duration-200 group-hover:rotate-45 group-hover:border-relay-acid/40 group-hover:text-relay-acid max-[760px]:right-6 max-[760px]:top-6"
                >
                  ↗
                </i>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section
        className="features-section relative z-[2] pb-[150px] pt-[clamp(110px,12vw,184px)] text-relay-paper max-[760px]:py-[96px] max-[760px]:pb-[90px]"
        id="features"
      >
        <div className="mx-auto w-[min(1240px,calc(100%_-_96px))] max-[760px]:w-[calc(100%_-_34px)]">
          <div className="max-w-[910px]">
            <span className="proof-eyebrow text-relay-acid">Designed for operators</span>
            <h2 className="mt-[22px] font-display text-[clamp(3rem,5.6vw,5.8rem)] font-normal leading-[0.96] tracking-[-0.062em] max-[760px]:text-[clamp(2.9rem,14vw,4.2rem)]">
              See the failure. Find the cause. Recover safely.
            </h2>
            <p className="mt-[27px] max-w-[610px] text-[clamp(1rem,1.3vw,1.12rem)] leading-[1.72] text-[#999f96]">
              Every view is shaped around the system guarantees in Relay’s
              architecture—not vanity totals or decorative charts.
            </p>
          </div>

          <div className="mt-[clamp(88px,10vw,140px)] max-[760px]:mt-[70px] [&>.feature-row:last-child]:border-b">
            <FeatureRow
              body="One tick per job, one row per priority lane. Density is backlog, color is state, and a stalled lane becomes obvious before starvation becomes an outage."
              eyebrow="Signature view"
              points={[
                "Watch strict priority drain order without hiding lower lanes.",
                "Spot the aging window that promotes long-waiting work.",
                "Keep rendering bounded while preserving backlog density.",
              ]}
              title="The lane tape makes pressure visible."
              visual={<LaneTapeVisual />}
            />

            <FeatureRow
              body="Hundreds of dead jobs from one bug are one incident. Relay groups failures by normalized error and handler so operators triage root causes instead of rows."
              eyebrow="Triage"
              points={[
                "Compare first-seen, last-seen, and affected job counts.",
                "Replay one job or a throttled, cancellable error cluster.",
                "Keep every attempt, stack trace, and payload reference.",
              ]}
              reverse
              title="A dead-letter queue that clusters itself."
              visual={<DlqVisual />}
            />

            <FeatureRow
              body="Rate, concurrency, priority, and schedule behavior live in one operational context. Controls explain their impact before an operator changes them."
              eyebrow="Control"
              points={[
                "Separate start-rate limits from in-flight concurrency caps.",
                "Preview schedule timezone and next-run behavior.",
                "Pause dispatch without rejecting new durable work.",
              ]}
              title="Guardrails without a control-plane maze."
              visual={<ControlsVisual />}
            />

            <FeatureRow
              body="A claimed job holds a renewable lease. If its worker disappears, the reaper detects the stale deadline and returns the work safely without losing the durable record."
              eyebrow="Correctness"
              points={[
                "Heartbeat and lease renewal stay visible as separate facts.",
                "Three reclaims park a poison job instead of harming the fleet.",
                "The reconciler can rebuild Redis state from Postgres truth.",
              ]}
              reverse
              title="Failure recovery you can explain."
              visual={<RecoveryVisual />}
            />

            <FeatureRow
              body="Declare parents when work is enqueued. Relay releases a child when its dependency counter reaches zero, supporting fan-out and fan-in without polling the job table."
              eyebrow="The differentiator"
              points={[
                "Understand blocked work from the graph, not hidden counters.",
                "Reject cycles before execution and identify the offending path.",
                "Apply parent-failure policy once across the downstream subtree.",
              ]}
              title="Dependency chains, rendered as a story."
              visual={<DependencyVisual />}
            />

            <FeatureRow
              body="Relay restores the enqueue request’s trace context when a worker begins execution, preserving one waterfall across the asynchronous queue boundary."
              eyebrow="The headline"
              points={[
                "See API time, database commit, queue wait, and handler runtime.",
                "Make queue dwell time a measured span instead of a mystery gap.",
                "Connect every state transition to metrics and live events.",
              ]}
              reverse
              title="One trace from request to result."
              visual={<TraceVisual />}
            />
          </div>
        </div>
      </section>
    </>
  );
}
