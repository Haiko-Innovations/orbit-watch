import { useState } from "react";
import { type ChainInfo, getJson, type OpenRequest, postJson, type Session } from "../api";
import type { Prepared } from "../chain/describe";
import { actionKey, SendFlow } from "../components/SendFlow";
import { Loaded } from "../components/Status";
import { formatAmount, formatUtc } from "../format";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.openRequests;

async function loadOpenRequests(): Promise<OpenRequest[]> {
  return (await getJson<{ requests: OpenRequest[] }>("/v1/public/open-requests")).requests;
}

/** A station reserves a funded request with its own wallet (step 3.5). */
function Reserve({
  item,
  chain,
  session,
}: {
  item: OpenRequest;
  chain: ChainInfo;
  session: Session;
}) {
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (prepared) {
    return (
      <SendFlow
        prepared={prepared}
        chain={chain}
        session={session}
        onDone={() => {
          window.location.hash = paths.request(item.request_id);
        }}
        onCancel={() => setPrepared(null)}
      />
    );
  }
  async function reserve() {
    setBusy(true);
    setProblem(null);
    try {
      setPrepared(
        await postJson<Prepared>(
          `/v1/requests/${encodeURIComponent(item.request_id)}/reserve`,
          {},
          { idempotencyKey: actionKey() },
        ),
      );
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="actions">
      <button type="button" disabled={busy} onClick={() => void reserve()}>
        {strings.reserve.button(item.request_id)}
      </button>
      <span className="muted">{strings.reserve.note}</span>
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
    </div>
  );
}

function RequestCard({
  item,
  chain,
  session,
}: {
  item: OpenRequest;
  chain: ChainInfo | null;
  session: Session | null;
}) {
  const { request, terms, split } = item;
  const token = chain ? chain.token : null;
  const titleId = `request-${item.request_id}`;
  const requirements = request.requirements ?? {};
  const listed = [
    requirements.min_observations === undefined
      ? null
      : s.minObservations(requirements.min_observations),
    requirements.max_angle_uncertainty_arcsec === undefined
      ? null
      : s.maxAngle(requirements.max_angle_uncertainty_arcsec),
  ].filter((text): text is string => text !== null);
  return (
    <article className="card" aria-labelledby={titleId}>
      <header className="card-header">
        <h2 id={titleId}>{request.title ?? item.request_id}</h2>
        {item.simulated ? <span className="badge">{strings.simulated}</span> : null}
      </header>
      <p className="card-meta">
        <code>{item.request_id}</code> ·{" "}
        <span className={`state state-${item.status}`}>
          {item.status === "funded" ? s.funded : s.open}
        </span>
      </p>
      <dl className="details compact">
        <dt>{s.target}</dt>
        <dd>
          {request.target.name ?? "NORAD"} <span className="muted">({terms.target_norad_id})</span>
        </dd>
        <dt>{s.window}</dt>
        <dd>
          {formatUtc(terms.window_start)} – {formatUtc(terms.window_end)}
        </dd>
        <dt>{s.deadline}</dt>
        <dd>{formatUtc(terms.delivery_deadline)}</dd>
        <dt>{s.observerReward}</dt>
        <dd>{split ? formatAmount(split.observer, token) : s.notFunded}</dd>
        <dt>{s.reviewerReward}</dt>
        <dd>{split ? formatAmount(split.reviewer, token) : s.notFunded}</dd>
        {listed.length > 0 ? (
          <>
            <dt>{s.requirements}</dt>
            <dd>{listed.join(", ")}</dd>
          </>
        ) : null}
        <dt>{s.requester}</dt>
        <dd>
          <code>{item.requester}</code>
        </dd>
      </dl>
      {session?.role === "station" && chain !== null && item.status === "funded" ? (
        <Reserve item={item} chain={chain} session={session} />
      ) : null}
    </article>
  );
}

export function OpenRequestsPage({
  chain,
  session = null,
}: {
  chain: ChainInfo | null;
  session?: Session | null;
}) {
  const [requests, reload] = useResource(loadOpenRequests);
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <Loaded resource={requests} reload={reload}>
        {(items) =>
          items.length === 0 ? (
            <p>{s.none}</p>
          ) : (
            <div className="cards">
              {items.map((item) => (
                <RequestCard key={item.request_id} item={item} chain={chain} session={session} />
              ))}
            </div>
          )
        }
      </Loaded>
    </>
  );
}
