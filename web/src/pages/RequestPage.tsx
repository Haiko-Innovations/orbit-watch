import { useCallback, useId, useState } from "react";
import {
  ApiError,
  type ChainInfo,
  getJson,
  postFile,
  postJson,
  type RequestDocument,
  type RequestView,
  type Session,
  type VerificationReport,
} from "../api";
import type { Prepared } from "../chain/describe";
import { actionKey, SendFlow } from "../components/SendFlow";
import { Loaded, MaybeLink } from "../components/Status";
import { formatAmount, formatUnits, formatUtc, parseUnits, shortHex } from "../format";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.request;
const REVIEWS_PER_ROUND = 3n;

interface RequestData {
  view: RequestView;
  /** The request document, which only the request's parties may read before publication. */
  document: RequestDocument | null;
}

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** What happened so far, in order, from the lifecycle record. */
function Progress({ view }: { view: RequestView }) {
  const record = view.record;
  const lines: string[] = [];
  if (record.reserved_by && !record.delivered_at) {
    lines.push(
      s.reservedBy(
        record.reserved_by,
        record.reservation_expires_at ? formatUtc(record.reservation_expires_at) : null,
      ),
    );
  }
  if (record.observer && record.delivered_at) {
    lines.push(s.deliveredBy(record.observer, formatUtc(record.delivered_at)));
  }
  if (record.automated_verdict) lines.push(s.verdict(record.automated_verdict));
  if (record.status === "challenge_period" && record.challenge_deadline) {
    lines.push(s.challengeUntil(formatUtc(record.challenge_deadline)));
  }
  if (record.challenger) lines.push(s.challengedBy(record.challenger));
  if (record.reviewers.length > 0) lines.push(s.reviewers(record.reviewers.join(", ")));
  if (record.status === "in_review" && record.review_deadline) {
    lines.push(s.reviewUntil(formatUtc(record.review_deadline)));
  }
  if (record.outcome) {
    lines.push(
      `${s.outcome(record.outcome)}${record.outcome_reason ? `: ${record.outcome_reason}` : ""}`,
    );
  }
  if (lines.length === 0) return null;
  return (
    <>
      <h2>{s.progress}</h2>
      <ol className="progress-list">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ol>
    </>
  );
}

function FundForm({
  chain,
  requestId,
  onPrepared,
}: {
  chain: ChainInfo;
  requestId: string;
  onPrepared: (p: Prepared) => void;
}) {
  const [observer, setObserver] = useState("1");
  const [reviewer, setReviewer] = useState("0.1");
  const [fee, setFee] = useState("0");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const ids = { observer: useId(), reviewer: useId(), fee: useId() };
  const decimals = chain.token.decimals;
  const units = [observer, reviewer, fee].map((value) => parseUnits(value, decimals));
  const [o, r, f] = units;
  const valid =
    o !== null &&
    r !== null &&
    f !== null &&
    o !== undefined &&
    r !== undefined &&
    f !== undefined &&
    o > 0n;
  const token = chain.token;

  async function prepare(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setProblem(null);
    try {
      onPrepared(
        await postJson<Prepared>(
          `/v1/requests/${encodeURIComponent(requestId)}/fund`,
          { observer: Number(o), reviewer: Number(r), platform_fee: Number(f) },
          { idempotencyKey: actionKey() },
        ),
      );
    } catch (error) {
      setProblem(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={prepare} aria-labelledby={`${ids.observer}-title`}>
      <h2 id={`${ids.observer}-title`}>{s.fundTitle}</h2>
      <p className="muted">{s.fundIntro}</p>
      <div className="field-row">
        <div className="field">
          <label htmlFor={ids.observer}>
            {s.observerReward} ({token.symbol})
          </label>
          <input
            id={ids.observer}
            inputMode="decimal"
            value={observer}
            onChange={(e) => setObserver(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.reviewer}>
            {s.reviewerReward} ({token.symbol})
          </label>
          <input
            id={ids.reviewer}
            inputMode="decimal"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.fee}>
            {s.platformFee} ({token.symbol})
          </label>
          <input
            id={ids.fee}
            inputMode="decimal"
            value={fee}
            onChange={(e) => setFee(e.target.value)}
          />
        </div>
      </div>
      {valid ? (
        <div aria-live="polite">
          <p>
            <strong>
              {s.deposit(`${formatUnits(o + REVIEWS_PER_ROUND * r + f, decimals)} ${token.symbol}`)}
            </strong>
          </p>
          <p className="muted">
            {s.depositSplit(
              `${formatUnits(o, decimals)} ${token.symbol}`,
              `${formatUnits(REVIEWS_PER_ROUND * r, decimals)} ${token.symbol}`,
              `${formatUnits(f, decimals)} ${token.symbol}`,
            )}
          </p>
        </div>
      ) : (
        <p className="problem">{strings.newRequest.invalid}</p>
      )}
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
      <div className="actions">
        <button type="submit" disabled={!valid || busy}>
          {s.prepareFunding}
        </button>
      </div>
    </form>
  );
}

function ChallengeForm({
  requestId,
  intro,
  onPrepared,
}: {
  requestId: string;
  intro: string;
  onPrepared: (p: Prepared) => void;
}) {
  const [reason, setReason] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const reasonId = useId();
  const titleId = useId();
  async function prepare(event: React.FormEvent) {
    event.preventDefault();
    if (!reason.trim()) return;
    setBusy(true);
    setProblem(null);
    try {
      onPrepared(
        await postJson<Prepared>(
          `/v1/requests/${encodeURIComponent(requestId)}/challenge`,
          { reason: reason.trim() },
          { idempotencyKey: actionKey() },
        ),
      );
    } catch (error) {
      setProblem(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="panel" onSubmit={prepare} aria-labelledby={titleId}>
      <h2 id={titleId}>{s.challengeTitle}</h2>
      <p className="muted">{intro}</p>
      <label htmlFor={reasonId}>{s.reason}</label>
      <textarea
        id={reasonId}
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        rows={3}
        maxLength={2000}
        required
      />
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
      <div className="actions">
        <button type="submit" disabled={busy || !reason.trim()}>
          {s.prepareChallenge}
        </button>
      </div>
    </form>
  );
}

function RequesterActions({
  view,
  chain,
  session,
  reload,
}: {
  view: RequestView;
  chain: ChainInfo;
  session: Session;
  reload: () => void;
}) {
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const record = view.record;
  const id = record.request_id;
  const base = `/v1/requests/${encodeURIComponent(id)}`;

  if (prepared) {
    const close = () => {
      setPrepared(null);
      reload();
    };
    return (
      <SendFlow
        prepared={prepared}
        chain={chain}
        session={session}
        onDone={close}
        onCancel={close}
      />
    );
  }

  async function act(path: string) {
    setBusy(true);
    setProblem(null);
    try {
      const answer = await postJson<Prepared | RequestView>(
        `${base}/${path}`,
        {},
        { idempotencyKey: actionKey() },
      );
      if ("sign" in answer) setPrepared(answer);
      else reload();
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : errorText(error));
    } finally {
      setBusy(false);
    }
  }

  const status = record.status;
  const cancellable = status === "draft" || status === "open" || status === "funded";
  return (
    <>
      {status === "draft" ? (
        <div className="panel">
          <p>{s.publishNote}</p>
          <button type="button" disabled={busy} onClick={() => void act("open")}>
            {s.publish}
          </button>
        </div>
      ) : null}
      {status === "open" ? (
        <FundForm chain={chain} requestId={id} onPrepared={setPrepared} />
      ) : null}
      {status === "challenge_period" && record.automated_verdict === "pass" ? (
        <ChallengeForm requestId={id} intro={s.challengeIntro} onPrepared={setPrepared} />
      ) : null}
      {cancellable ? (
        <p>
          <button
            type="button"
            className="secondary"
            disabled={busy}
            onClick={() => void act("cancel")}
          >
            {s.cancel}
          </button>{" "}
          <span className="muted">{s.cancelNote}</span>
        </p>
      ) : null}
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
    </>
  );
}

async function sha256Hex(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function formatOf(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".iod") || lower.endsWith(".txt")) return "iod";
  if (lower.endsWith(".tdm") || lower.endsWith(".kvn") || lower.endsWith(".xml")) return "tdm";
  return "json";
}

function saysSimulated(bytes: Uint8Array): boolean {
  try {
    return (
      (JSON.parse(new TextDecoder().decode(bytes)) as { simulated?: unknown }).simulated === true
    );
  } catch {
    return /simulated\s*=\s*true/i.test(new TextDecoder().decode(bytes.slice(0, 4096)));
  }
}

interface Chosen {
  name: string;
  bytes: Uint8Array;
  sha256: string;
  format: string;
}

function DeliveryForm({
  requestId,
  onPrepared,
}: {
  requestId: string;
  onPrepared: (prepared: Prepared, sha256: string) => void;
}) {
  const d = strings.delivery;
  const ids = { file: useId(), format: useId(), title: useId() };
  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const base = `/v1/requests/${encodeURIComponent(requestId)}`;

  async function choose(name: string, bytes: Uint8Array, format?: string) {
    setChosen({ name, bytes, sha256: await sha256Hex(bytes), format: format ?? formatOf(name) });
  }

  async function simulate() {
    setBusy(true);
    setProblem(null);
    try {
      const made = await postJson<{ file_name: string; observations: string }>(
        `${base}/simulate`,
        {},
      );
      await choose(made.file_name, new TextEncoder().encode(made.observations), "json");
    } catch (error) {
      setProblem(
        error instanceof ApiError && error.code === "no_profile" ? d.noProfile : errorText(error),
      );
    } finally {
      setBusy(false);
    }
  }

  async function prepare(event: React.FormEvent) {
    event.preventDefault();
    if (!chosen) return;
    setBusy(true);
    setProblem(null);
    try {
      const prepared = await postFile<Prepared>(
        `${base}/deliveries?format=${chosen.format}`,
        chosen.bytes,
        chosen.sha256,
        actionKey(),
      );
      onPrepared(prepared, chosen.sha256);
    } catch (error) {
      setProblem(errorText(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={prepare} aria-labelledby={ids.title}>
      <h2 id={ids.title}>{d.title}</h2>
      <p className="muted">{d.intro}</p>
      <div className="field">
        <label htmlFor={ids.file}>{d.file}</label>
        <input
          id={ids.file}
          type="file"
          accept=".json,.iod,.txt,.tdm,.kvn,.xml"
          onChange={async (event) => {
            const file = event.target.files?.[0];
            if (file) await choose(file.name, new Uint8Array(await file.arrayBuffer()));
          }}
        />
      </div>
      <p>
        <button type="button" className="secondary" disabled={busy} onClick={() => void simulate()}>
          {d.simulate}
        </button>{" "}
        <span className="muted">{d.simulateNote}</span>
      </p>
      {chosen ? (
        <div aria-live="polite">
          <p>
            <strong>{d.chosen(chosen.name, chosen.bytes.length)}</strong>{" "}
            {saysSimulated(chosen.bytes) ? (
              <span className="badge">{strings.simulated}</span>
            ) : null}
          </p>
          <p>
            {d.sha}:{" "}
            <code className="hex" data-testid="delivery-sha256">
              {chosen.sha256}
            </code>
          </p>
          <div className="field">
            <label htmlFor={ids.format}>{d.format}</label>
            <select
              id={ids.format}
              value={chosen.format}
              onChange={(e) => setChosen({ ...chosen, format: e.target.value })}
            >
              {Object.entries(d.formats).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
        </div>
      ) : null}
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
      <div className="actions">
        <button type="submit" disabled={busy || chosen === null}>
          {d.prepare}
        </button>
      </div>
    </form>
  );
}

function ObserverActions({
  view,
  chain,
  session,
  reload,
}: {
  view: RequestView;
  chain: ChainInfo;
  session: Session;
  reload: () => void;
}) {
  const [prepared, setPrepared] = useState<{ prepared: Prepared; sha256?: string } | null>(null);
  const record = view.record;
  const id = record.request_id;
  if (prepared) {
    const close = () => {
      setPrepared(null);
      reload();
    };
    return (
      <SendFlow
        prepared={prepared.prepared}
        chain={chain}
        session={session}
        expected={prepared.sha256 ? { deliverySha256: prepared.sha256 } : {}}
        onDone={close}
        onCancel={close}
      />
    );
  }
  if (record.status === "reserved" && record.reserved_by === session.party) {
    return (
      <DeliveryForm
        requestId={id}
        onPrepared={(next, sha256) => setPrepared({ prepared: next, sha256 })}
      />
    );
  }
  if (
    record.status === "challenge_period" &&
    record.observer === session.party &&
    record.automated_verdict === "fail"
  ) {
    return (
      <ChallengeForm
        requestId={id}
        intro={s.observerChallengeIntro}
        onPrepared={(next) => setPrepared({ prepared: next })}
      />
    );
  }
  return null;
}

/** The automated verification's checks, with their reasons: why it passed or failed. */
function Verification({ sha }: { sha: string }) {
  const v = strings.verification;
  const load = useCallback(() => getJson<VerificationReport>(`/v1/files/${sha}`), [sha]);
  const [report, reload] = useResource(load);
  return (
    <>
      <h2>{v.title}</h2>
      <Loaded resource={report} reload={reload}>
        {(value) => (
          <>
            <p>
              <strong>{v.verdict(value.verdict)}</strong> · {value.summary}
            </p>
            <ul className="checks">
              {value.checks.map((check) => (
                <li key={check.id} className={`check check-${check.result}`}>
                  <strong>
                    {check.title}: {v.results[check.result] ?? check.result}
                  </strong>
                  <span>{check.reason}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </Loaded>
    </>
  );
}

function Files({ view }: { view: RequestView }) {
  const record = view.record;
  const id = record.request_id;
  const files = [
    { label: s.requestFile, sha: record.terms.request_sha256, name: `${id}-request.json` },
    record.delivery_sha256
      ? { label: s.observations, sha: record.delivery_sha256, name: `${id}-observations` }
      : null,
    record.report_sha256
      ? { label: s.report, sha: record.report_sha256, name: `${id}-report.json` }
      : null,
  ].filter((file) => file !== null);
  return (
    <>
      <h2>{s.files}</h2>
      <ul className="file-list">
        {files.map((file) => (
          <li key={file.sha}>
            <a href={`/v1/files/${file.sha}`} download={file.name}>
              {file.label}
            </a>{" "}
            <code className="muted">{shortHex(file.sha)}</code>
          </li>
        ))}
      </ul>
    </>
  );
}

function Payments({ view, chain }: { view: RequestView; chain: ChainInfo }) {
  const plan = view.summary.settlement?.plan;
  const events = view.chain?.events ?? [];
  return (
    <>
      <h2>{s.payments}</h2>
      {plan ? (
        <ul>
          {plan.payouts.map((payout) => (
            <li key={`${payout.party}-${payout.reason}`}>
              {s.paidOut(
                payout.party,
                formatAmount(payout.points, chain.token),
                s.reasons[payout.reason] ?? payout.reason,
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="muted">{s.notSettled}</p>
      )}
      {events.length > 0 ? (
        <>
          <h2>{s.chainEvents}</h2>
          <ul className="file-list">
            {events.map((event) => (
              <li key={`${event.tx_hash}-${event.event}`}>
                {event.event} · {formatUtc(event.at)} ·{" "}
                <MaybeLink href={event.explorer}>
                  <code>{shortHex(event.tx_hash)}</code>
                </MaybeLink>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </>
  );
}

export function RequestPage({
  id,
  chain,
  session,
}: {
  id: string;
  chain: ChainInfo;
  session: Session;
}) {
  const load = useCallback(async (): Promise<RequestData> => {
    const view = await getJson<RequestView>(`/v1/requests/${encodeURIComponent(id)}`);
    try {
      const document = await getJson<RequestDocument>(
        `/v1/files/${view.record.terms.request_sha256}`,
      );
      return { view, document };
    } catch (error) {
      if (error instanceof ApiError && error.code === "unknown_file") {
        return { view, document: null };
      }
      throw error;
    }
  }, [id]);
  const [loaded, reload] = useResource(load);
  return (
    <Loaded resource={loaded} reload={reload}>
      {({ view, document }) => {
        const record = view.record;
        const terms = record.terms;
        const mine = record.requester === session.party;
        const requirements = document?.requirements ?? {};
        return (
          <>
            <h1 tabIndex={-1}>{document?.title ?? record.request_id}</h1>
            <p className="card-meta">
              <code>{record.request_id}</code>
              {document?.simulated ? <span className="badge">{strings.simulated}</span> : null}
            </p>
            {document === null ? <p className="muted">{s.notYours}</p> : null}
            <p className="status-line">
              <strong>{s.status[record.status] ?? record.status}</strong>
              {record.outcome ? ` · ${s.outcome(record.outcome)}` : ""}
            </p>
            <Progress view={view} />
            {mine ? (
              <RequesterActions view={view} chain={chain} session={session} reload={reload} />
            ) : null}
            {record.reserved_by === session.party || record.observer === session.party ? (
              <ObserverActions view={view} chain={chain} session={session} reload={reload} />
            ) : null}
            {document !== null && record.report_sha256 ? (
              <Verification sha={record.report_sha256} />
            ) : null}
            <h2>{s.terms}</h2>
            <dl className="details">
              <dt>{s.target}</dt>
              <dd>
                {document?.target.name ?? "NORAD"}{" "}
                <span className="muted">({terms.target_norad_id})</span>
              </dd>
              <dt>{s.window}</dt>
              <dd>
                {formatUtc(terms.window_start)} – {formatUtc(terms.window_end)}
              </dd>
              <dt>{s.deadline}</dt>
              <dd>{formatUtc(terms.delivery_deadline)}</dd>
              <dt>{s.requirements}</dt>
              <dd>
                {[
                  requirements.min_observations === undefined
                    ? null
                    : strings.openRequests.minObservations(requirements.min_observations),
                  requirements.max_angle_uncertainty_arcsec === undefined
                    ? null
                    : strings.openRequests.maxAngle(requirements.max_angle_uncertainty_arcsec),
                ]
                  .filter(Boolean)
                  .join(", ")}
              </dd>
              <dt>{s.reservation}</dt>
              <dd>{s.hours(terms.reservation_hours)}</dd>
              <dt>{s.challenge}</dt>
              <dd>{s.hours(terms.challenge_period_hours)}</dd>
              <dt>{s.review}</dt>
              <dd>{s.hours(terms.review_hours)}</dd>
              <dt>{s.embargo}</dt>
              <dd>{s.days(terms.embargo_days)}</dd>
            </dl>
            {document !== null ? <Files view={view} /> : null}
            <Payments view={view} chain={chain} />
            {mine ? (
              <p>
                <a href={paths.myRequests}>{s.back}</a>
              </p>
            ) : null}
          </>
        );
      }}
    </Loaded>
  );
}
