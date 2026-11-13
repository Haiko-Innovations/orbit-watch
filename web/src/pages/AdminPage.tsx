import { useCallback, useId, useState } from "react";
import {
  type AdminOverview,
  ApiError,
  type CallData,
  type DemoDataset,
  type GovernanceView,
  getJson,
  type Proposal,
  postJson,
  type Session,
  type SimulatedFile,
  type StationProfile,
  type Target,
  type TimelockOperation,
} from "../api";
import { DownloadLink } from "../components/Download";
import { actionKey } from "../components/SendFlow";
import { Loaded, MaybeLink } from "../components/Status";
import { addressLink, formatAmount, formatUtc, shortHex, utcFromInput } from "../format";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.admin;
// The demo datasets' good station: a CMOS camera with GPS timing.
const DEFAULT_PROFILE = "sim-cmos-gps";
const g = s.governance;

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : String(error);
}

function Problem({ text }: { text: string | null }) {
  return text ? (
    <p className="problem" role="alert">
      {text}
    </p>
  ) : null;
}

// ---------------------------------------------------------------- requests and the chain

function Tick({ onDone }: { onDone: () => void }) {
  const [result, setResult] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function tick() {
    setBusy(true);
    setProblem(null);
    setResult(null);
    try {
      const done = await postJson<{ changed: string[]; sent?: string[] }>(
        "/v1/admin/tick",
        {},
        { idempotencyKey: actionKey() },
      );
      setResult(s.tick.done(done.changed.length, done.sent?.length ?? 0));
      onDone();
    } catch (error) {
      setProblem(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel" aria-labelledby="tick-title">
      <h2 id="tick-title">{s.tick.title}</h2>
      <p className="muted">{s.tick.intro}</p>
      <div className="actions">
        <button type="button" onClick={tick} disabled={busy}>
          {s.tick.button}
        </button>
      </div>
      {result ? (
        <p className="ok" role="status">
          {result}
        </p>
      ) : null}
      <Problem text={problem} />
    </section>
  );
}

function RequestsTable({ overview }: { overview: AdminOverview }) {
  const token = overview.chain?.token ?? null;
  if (overview.requests.length === 0) return <p className="muted">{s.none}</p>;
  const counts = Object.entries(overview.counts)
    .map(([status, n]) => `${n} ${status.replaceAll("_", " ")}`)
    .join(", ");
  return (
    <>
      <p>
        {s.count(overview.requests.length)}: {counts}
      </p>
      <div className="table-wrap">
        <table aria-label={s.overview}>
          <thead>
            <tr>
              <th scope="col">{s.request}</th>
              <th scope="col">{s.status}</th>
              <th scope="col">{s.observer}</th>
              <th scope="col">{s.verdict}</th>
              <th scope="col">{s.outcome}</th>
            </tr>
          </thead>
          <tbody>
            {overview.requests.map((item) => (
              <tr key={item.request_id}>
                <td>
                  <code>{item.request_id}</code>
                  <br />
                  <span className="muted">{item.title ?? item.requester}</span>
                </td>
                <td>
                  {strings.request.status[item.status] ?? item.status}
                  {item.on_chain ? <span className="muted"> · {s.onChain}</span> : null}
                </td>
                <td>{item.observer ?? item.reserved_by ?? "–"}</td>
                <td>
                  {item.automated_verdict ?? "–"}
                  {item.votes.length > 0 ? (
                    <>
                      <br />
                      <span className="muted">
                        {s.votes(item.votes.filter(([, yes]) => yes).length, item.votes.length)}
                      </span>
                    </>
                  ) : null}
                </td>
                <td>
                  {item.outcome ? strings.request.outcome(item.outcome) : "–"}
                  {item.settlement ? (
                    <ul className="plain-list">
                      {item.settlement.plan.payouts
                        .filter((payout) => payout.points > 0)
                        .map((payout) => (
                          <li key={`${payout.party}-${payout.reason}`}>
                            {s.payout(
                              payout.party,
                              formatAmount(payout.points, token),
                              payout.reason,
                            )}
                          </li>
                        ))}
                    </ul>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Problems({ overview }: { overview: AdminOverview }) {
  const failed = overview.transactions.filter((t) => t.status === "failed");
  if (overview.conflicts.length === 0 && failed.length === 0) {
    return <p className="muted">{s.noProblems}</p>;
  }
  return (
    <ul className="tx-list">
      {overview.conflicts.map((conflict) => (
        <li key={`${conflict.tx_hash}-${conflict.code}`}>
          <strong>{s.conflict}</strong> <code>{conflict.request_id}</code>{" "}
          <code>{conflict.code}</code>: {conflict.message}
        </li>
      ))}
      {failed.map((tx) => (
        <li key={tx.tx_hash}>
          <strong>{s.failed}</strong> <code>{tx.action}</code> {tx.request_id ?? ""} ({tx.party}
          ): <code>{tx.error ?? "?"}</code>{" "}
          <MaybeLink href={tx.explorer}>
            <code>{shortHex(tx.tx_hash)}</code>
          </MaybeLink>
        </li>
      ))}
    </ul>
  );
}

function Transactions({ overview }: { overview: AdminOverview }) {
  if (overview.transactions.length === 0) {
    return <p className="muted">{strings.transactions.none}</p>;
  }
  return (
    <div className="table-wrap">
      <table aria-label={s.transactions}>
        <thead>
          <tr>
            <th scope="col">{s.party}</th>
            <th scope="col">{strings.transactions.action}</th>
            <th scope="col">{strings.transactions.request}</th>
            <th scope="col">{strings.transactions.status}</th>
            <th scope="col">{strings.transactions.transaction}</th>
          </tr>
        </thead>
        <tbody>
          {overview.transactions.map((tx) => (
            <tr key={tx.tx_hash}>
              <td>{tx.party}</td>
              <td>
                <code>{tx.action}</code>
              </td>
              <td>{tx.request_id ?? "–"}</td>
              <td className={`tx-${tx.status}`}>{strings.transactions.states[tx.status]}</td>
              <td>
                <MaybeLink href={tx.explorer}>
                  <code>{shortHex(tx.tx_hash)}</code>
                </MaybeLink>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EventLog({ overview }: { overview: AdminOverview }) {
  if (overview.events.length === 0) return <p className="muted">{s.noEvents}</p>;
  return (
    <div className="table-wrap">
      <table aria-label={s.events}>
        <thead>
          <tr>
            <th scope="col">{s.time}</th>
            <th scope="col">{s.request}</th>
            <th scope="col">{s.event}</th>
            <th scope="col">{s.block}</th>
          </tr>
        </thead>
        <tbody>
          {overview.events.map((event) => (
            <tr key={`${event.tx_hash}-${event.event}-${event.block}-${event.request_id}`}>
              <td>{formatUtc(event.at)}</td>
              <td>
                <code>{event.request_id}</code>
              </td>
              <td>
                <MaybeLink href={event.explorer}>{event.event}</MaybeLink>
              </td>
              <td>{event.block}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Overview() {
  const load = useCallback(() => getJson<AdminOverview>("/v1/admin/overview"), []);
  const [overview, reload] = useResource(load);
  return (
    <>
      <h2>{s.overview}</h2>
      <Loaded resource={overview} reload={reload}>
        {(value) => <RequestsTable overview={value} />}
      </Loaded>
      {/* Outside the loaded part, so that its result stays while the overview reloads. */}
      <Tick onDone={reload} />
      <Loaded resource={overview} reload={reload}>
        {(value) => (
          <>
            <h2>{s.problems}</h2>
            <Problems overview={value} />
            <h2>{s.transactions}</h2>
            <Transactions overview={value} />
            <h2>{s.events}</h2>
            <p className="muted">{s.eventsIntro}</p>
            <EventLog overview={value} />
          </>
        )}
      </Loaded>
    </>
  );
}

// ---------------------------------------------------------------- governance

function CallDetails({ call }: { call: CallData }) {
  return (
    <dl className="details compact">
      <dt>{g.to}</dt>
      <dd>
        <code className="hex">{call.to}</code>
      </dd>
      <dt>{g.value}</dt>
      <dd>
        <code>{call.value}</code>
      </dd>
      <dt>{g.data}</dt>
      <dd>
        <code className="hex">{call.data}</code>
      </dd>
    </dl>
  );
}

function batchText(batch: unknown): string {
  return `${JSON.stringify(batch, null, 2)}\n`;
}

function ProposalForm({ onPrepared }: { onPrepared: (proposal: Proposal) => void }) {
  const ids = { title: useId(), reviewer: useId(), hint: useId() };
  const [action, setAction] = useState<"add" | "remove">("add");
  const [reviewer, setReviewer] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function prepare(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setProblem(null);
    try {
      const reply = await postJson<{ proposal: Proposal }>("/v1/admin/governance/proposals", {
        action,
        reviewer: reviewer.trim(),
      });
      onPrepared(reply.proposal);
    } catch (error) {
      setProblem(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="panel" onSubmit={prepare} aria-labelledby={ids.title}>
      <h3 id={ids.title}>{g.proposeTitle}</h3>
      <fieldset>
        <legend>{g.action}</legend>
        <label className="choice">
          <input
            type="radio"
            name="governance-action"
            checked={action === "add"}
            onChange={() => setAction("add")}
          />
          {g.add}
        </label>
        <label className="choice">
          <input
            type="radio"
            name="governance-action"
            checked={action === "remove"}
            onChange={() => setAction("remove")}
          />
          {g.remove}
        </label>
      </fieldset>
      <label htmlFor={ids.reviewer}>{g.reviewer}</label>
      <input
        id={ids.reviewer}
        value={reviewer}
        onChange={(e) => setReviewer(e.target.value)}
        aria-describedby={ids.hint}
        autoComplete="off"
        spellCheck={false}
        required
      />
      <p id={ids.hint} className="muted">
        {g.reviewerHint}
      </p>
      <Problem text={problem} />
      <div className="actions">
        <button type="submit" disabled={busy || !reviewer.trim()}>
          {g.prepare}
        </button>
      </div>
    </form>
  );
}

function PreparedProposal({ proposal }: { proposal: Proposal }) {
  return (
    <section className="panel" aria-labelledby="proposal-title" role="status">
      <h3 id="proposal-title">{g.proposal(proposal.call.function)}</h3>
      <ol>
        {g.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <div className="actions">
        <DownloadLink
          text={batchText(proposal.batch_file)}
          name={`orbit-watch-${proposal.action}-reviewer-${proposal.reviewer.slice(2, 10)}.json`}
        >
          {g.download}
        </DownloadLink>
        {proposal.safe?.app ? (
          <a href={proposal.safe.app.home} target="_blank" rel="noopener noreferrer">
            {g.safeApp}
          </a>
        ) : null}
      </div>
      <CallDetails call={proposal.schedule} />
      <dl className="details compact">
        <dt>{g.operationId}</dt>
        <dd>
          <code className="hex">{proposal.operation_id}</code>
        </dd>
        <dt>{g.salt}</dt>
        <dd>
          <code className="hex">{proposal.salt}</code>
        </dd>
        <dt>{g.delay}</dt>
        <dd>{g.seconds(proposal.delay_seconds)}</dd>
      </dl>
    </section>
  );
}

function Operation({ operation }: { operation: TimelockOperation }) {
  const state = g.states[operation.state] ?? operation.state;
  return (
    <li className="card">
      <div className="card-header">
        <strong>{operation.calls.map((call) => call.description).join("; ")}</strong>
        <span className={`badge state-${operation.state}`}>{state}</span>
      </div>
      <p className="card-meta">
        <code>{shortHex(operation.operation_id)}</code> ·{" "}
        {g.scheduled(formatUtc(operation.scheduled_at))}
        {operation.ready_at && operation.state !== "done"
          ? ` · ${g.readyAt(formatUtc(operation.ready_at))}`
          : ""}
        {operation.executed_at ? ` · ${g.executed(formatUtc(operation.executed_at))}` : ""}
      </p>
      {operation.execute && operation.execute_batch ? (
        <details>
          <summary>{g.executeTitle}</summary>
          <p className="muted">{g.executeIntro}</p>
          <CallDetails call={operation.execute} />
          <div className="actions">
            <DownloadLink
              text={batchText(operation.execute_batch)}
              name={`orbit-watch-execute-${operation.operation_id.slice(2, 10)}.json`}
            >
              {g.downloadExecute}
            </DownloadLink>
          </div>
        </details>
      ) : null}
    </li>
  );
}

function Governance() {
  const load = useCallback(() => getJson<GovernanceView>("/v1/admin/governance"), []);
  const [view, reload] = useResource(load);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  return (
    <>
      <h2>{g.title}</h2>
      <p className="muted">{g.intro}</p>
      <Loaded resource={view} reload={reload}>
        {(value) => {
          const { registry, safe } = value;
          const link = (address: string) => addressLink(value.explorer, address);
          return (
            <>
              <dl className="details">
                <dt>{g.registry}</dt>
                <dd>
                  <MaybeLink href={link(registry.address)}>
                    <code className="hex">{registry.address}</code>
                  </MaybeLink>
                </dd>
                <dt>{g.owner}</dt>
                <dd>
                  <MaybeLink href={link(registry.owner)}>
                    <code className="hex">{registry.owner}</code>
                  </MaybeLink>{" "}
                  ({registry.timelock ? g.ownerTimelock : g.ownerOther})
                </dd>
                {registry.timelock ? (
                  <>
                    <dt>{g.delay}</dt>
                    <dd>{g.seconds(registry.timelock.min_delay_seconds)}</dd>
                  </>
                ) : null}
                <dt>{g.safe}</dt>
                <dd>
                  {safe === null ? (
                    g.noSafe
                  ) : (
                    <>
                      <MaybeLink href={link(safe.address)}>
                        <code className="hex">{safe.address}</code>
                      </MaybeLink>
                      {safe.threshold !== undefined && safe.owners ? (
                        <>
                          <br />
                          {g.signers(safe.threshold, safe.owners.length)}
                        </>
                      ) : null}
                      {safe.problem ? <p className="problem">{safe.problem}</p> : null}
                      {safe.proposer === undefined ? null : (
                        <p className={safe.proposer ? "ok" : "problem"}>
                          {safe.proposer ? g.proposerYes : g.proposerNo}
                        </p>
                      )}
                      {safe.app ? (
                        <p>
                          <a href={safe.app.home} target="_blank" rel="noopener noreferrer">
                            {g.safeApp}
                          </a>{" "}
                          ·{" "}
                          <a href={safe.app.queue} target="_blank" rel="noopener noreferrer">
                            {g.safeQueue}
                          </a>
                        </p>
                      ) : (
                        <p className="muted">{g.noSafeApp}</p>
                      )}
                    </>
                  )}
                </dd>
              </dl>
              <h3>{g.reviewers(registry.reviewers.length, registry.max_reviewers)}</h3>
              <ul className="request-list">
                {registry.reviewers.map((reviewer) => (
                  <li key={reviewer.address}>
                    <span>{reviewer.party ?? g.unknownParty}</span>
                    <MaybeLink href={link(reviewer.address)}>
                      <code className="hex">{reviewer.address}</code>
                    </MaybeLink>
                  </li>
                ))}
              </ul>
              {registry.timelock ? (
                <>
                  <ProposalForm onPrepared={setProposal} />
                  {proposal ? <PreparedProposal proposal={proposal} /> : null}
                </>
              ) : null}
              <h3>{g.operations}</h3>
              <p className="muted">{g.operationsIntro}</p>
              <div className="actions">
                <button type="button" className="secondary" onClick={reload}>
                  {g.refresh}
                </button>
              </div>
              {value.operations.length === 0 ? (
                <p className="muted">{g.noOperations}</p>
              ) : (
                <ul className="cards">
                  {value.operations.map((operation) => (
                    <Operation key={operation.operation_id} operation={operation} />
                  ))}
                </ul>
              )}
            </>
          );
        }}
      </Loaded>
    </>
  );
}

// ---------------------------------------------------------------- simulator and demo data

function MadeFile({ file }: { file: SimulatedFile }) {
  return (
    <div className="panel" role="status">
      <p>
        <span className="badge">{strings.simulated}</span>{" "}
        {file.count !== undefined ? s.simulator.made(file.count) : null}
        {file.expected_verdict
          ? ` ${s.demo.expected(file.expected_verdict, file.expected_failures ?? [])}`
          : null}
      </p>
      <p className="muted">
        {s.sha} <code className="hex">{file.sha256}</code>
      </p>
      <DownloadLink text={file.observations} name={file.file_name}>
        {s.downloadFile(file.file_name)}
      </DownloadLink>
    </div>
  );
}

interface SimulatorInputs {
  templates: StationProfile[];
  targets: Target[];
  demo: DemoDataset[];
}

async function loadSimulatorInputs(): Promise<SimulatorInputs> {
  const [templates, targets, demo] = await Promise.all([
    getJson<{ templates: StationProfile[] }>("/v1/public/station-templates"),
    getJson<{ targets: Target[] }>("/v1/public/targets"),
    getJson<{ datasets: DemoDataset[] }>("/v1/admin/demo-datasets"),
  ]);
  return { templates: templates.templates, targets: targets.targets, demo: demo.datasets };
}

function SimulatorForm({ templates, targets }: Omit<SimulatorInputs, "demo">) {
  const ids = {
    title: useId(),
    profile: useId(),
    target: useId(),
    start: useId(),
    end: useId(),
    passes: useId(),
  };
  const [profile, setProfile] = useState(
    templates.find((template) => template.id === DEFAULT_PROFILE)?.id ?? templates[0]?.id ?? "",
  );
  const [target, setTarget] = useState(String(targets[0]?.norad_id ?? ""));
  const [start, setStart] = useState("2026-11-01T15:00");
  const [end, setEnd] = useState("2026-11-02T03:00");
  const [passes, setPasses] = useState("2");
  const [file, setFile] = useState<SimulatedFile | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function run(event: React.FormEvent) {
    event.preventDefault();
    const from = utcFromInput(start);
    const to = utcFromInput(end);
    if (from === null || to === null || from >= to) {
      setProblem(s.simulator.invalid);
      return;
    }
    setBusy(true);
    setProblem(null);
    setFile(null);
    try {
      setFile(
        await postJson<SimulatedFile>("/v1/admin/simulate", {
          profile,
          norad_id: Number(target),
          start: from,
          end: to,
          max_passes: Number(passes),
        }),
      );
    } catch (error) {
      setProblem(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="panel" onSubmit={run} aria-labelledby={ids.title}>
      <h3 id={ids.title}>{s.simulator.title}</h3>
      <p className="muted">{s.simulator.intro}</p>
      <div className="field-row">
        <div className="field">
          <label htmlFor={ids.profile}>{s.simulator.profile}</label>
          <select id={ids.profile} value={profile} onChange={(e) => setProfile(e.target.value)}>
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.id}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor={ids.target}>{s.simulator.target}</label>
          <select id={ids.target} value={target} onChange={(e) => setTarget(e.target.value)}>
            {targets.map((item) => (
              <option key={item.norad_id} value={item.norad_id}>
                {item.name ?? item.norad_id} ({item.norad_id})
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor={ids.start}>{s.simulator.start}</label>
          <input
            id={ids.start}
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.end}>{s.simulator.end}</label>
          <input
            id={ids.end}
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.passes}>{s.simulator.passes}</label>
          <input
            id={ids.passes}
            type="number"
            min={1}
            max={6}
            value={passes}
            onChange={(e) => setPasses(e.target.value)}
          />
        </div>
      </div>
      <Problem text={problem} />
      <div className="actions">
        <button type="submit" disabled={busy || !profile || !target}>
          {s.simulator.run}
        </button>
      </div>
      {file ? <MadeFile file={file} /> : null}
    </form>
  );
}

function DemoDatasets({ datasets }: { datasets: DemoDataset[] }) {
  const [made, setMade] = useState<SimulatedFile | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function make(name: string) {
    setBusy(true);
    setProblem(null);
    setMade(null);
    try {
      setMade(await postJson<SimulatedFile>(`/v1/admin/demo-datasets/${name}`, {}));
    } catch (error) {
      setProblem(message(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel" aria-labelledby="demo-title">
      <h3 id="demo-title">{s.demo.title}</h3>
      <p className="muted">{s.demo.intro}</p>
      <ul className="request-list">
        {datasets.map((dataset) => (
          <li key={dataset.name}>
            <span>
              <code>{dataset.name}</code>: {dataset.title}
            </span>
            <span className="muted">
              {s.demo.expected(dataset.expected_verdict, dataset.expected_failures)}
            </span>
            <span>
              <button
                type="button"
                className="secondary"
                disabled={busy}
                onClick={() => make(dataset.name)}
              >
                {s.demo.make(dataset.name)}
              </button>
            </span>
          </li>
        ))}
      </ul>
      <Problem text={problem} />
      {made ? <MadeFile file={made} /> : null}
    </section>
  );
}

function Simulation() {
  const [inputs, reload] = useResource(loadSimulatorInputs);
  return (
    <>
      <h2>{s.simulator.title}</h2>
      <Loaded resource={inputs} reload={reload}>
        {(value) => (
          <>
            <SimulatorForm templates={value.templates} targets={value.targets} />
            <DemoDatasets datasets={value.demo} />
          </>
        )}
      </Loaded>
    </>
  );
}

// ---------------------------------------------------------------- the page

export function AdminPage({ session, onChain }: { session: Session; onChain: boolean }) {
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      {session.role !== "admin" ? (
        <p className="problem" role="alert">
          {s.notAdmin}
        </p>
      ) : (
        <>
          <p className="lead">{s.intro}</p>
          <Overview />
          {onChain ? <Governance /> : null}
          <Simulation />
        </>
      )}
    </>
  );
}
