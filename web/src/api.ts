// The documented HTTP API of the service, on the page's own origin (decisions D-25, P3-06).
// The app uses nothing else.

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
  }
}

/** GET a JSON document from the API; refusals become an ApiError with the API's code. */
export async function getJson<T>(path: string, fetcher: typeof fetch = fetch): Promise<T> {
  return call<T>(path, { method: "GET" }, fetcher);
}

/** POST a JSON document. Changes to requests also send an Idempotency-Key (one per action). */
export async function postJson<T>(
  path: string,
  body: unknown,
  options: { idempotencyKey?: string } = {},
  fetcher: typeof fetch = fetch,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;
  return call<T>(path, { method: "POST", headers, body: JSON.stringify(body) }, fetcher);
}

/** PUT a JSON document (a change: one Idempotency-Key per action). */
export async function putJson<T>(
  path: string,
  body: unknown,
  idempotencyKey: string,
  fetcher: typeof fetch = fetch,
): Promise<T> {
  return call<T>(
    path,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json", "Idempotency-Key": idempotencyKey },
      body: JSON.stringify(body),
    },
    fetcher,
  );
}

/** POST a file as it is, with its SHA-256 for the service to check. */
export async function postFile<T>(
  path: string,
  body: Uint8Array,
  sha256: string,
  idempotencyKey: string,
  fetcher: typeof fetch = fetch,
): Promise<T> {
  return call<T>(
    path,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/octet-stream",
        "Content-SHA256": sha256,
        "Idempotency-Key": idempotencyKey,
      },
      body: body as BodyInit,
    },
    fetcher,
  );
}

export async function deleteJson<T>(path: string, fetcher: typeof fetch = fetch): Promise<T> {
  return call<T>(path, { method: "DELETE" }, fetcher);
}

// The session cookie travels by itself: same origin, HttpOnly (decision P3-04).
async function call<T>(path: string, init: RequestInit, fetcher: typeof fetch): Promise<T> {
  let response: Response;
  try {
    response = await fetcher(path, {
      ...init,
      credentials: "same-origin",
      headers: { Accept: "application/json", ...(init.headers as Record<string, string>) },
    });
  } catch (error) {
    throw new ApiError("unreachable", `The service could not be reached (${String(error)}).`, 0);
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = errorOf(body);
    throw new ApiError(
      detail?.code ?? "http_error",
      detail?.message ?? `The service answered ${response.status}.`,
      response.status,
    );
  }
  return body as T;
}

function errorOf(body: unknown): { code: string; message: string } | null {
  if (typeof body !== "object" || body === null || !("error" in body)) return null;
  const error = (body as { error: unknown }).error;
  if (typeof error !== "object" || error === null) return null;
  const { code, message } = error as { code?: unknown; message?: unknown };
  return typeof code === "string" && typeof message === "string" ? { code, message } : null;
}

export interface Health {
  status: string;
  version: string;
  notice: string;
}

export interface Token {
  address: string;
  symbol: string;
  decimals: number;
}

export interface ChainInfo {
  chain_id: number;
  network: string;
  notice: string;
  escrow: string;
  registry: string;
  token: Token;
  eas: string;
  result_schema: string;
  vote_schema: string;
  verifier: string;
  fee_recipient: string;
  explorer: string | null;
  local: boolean;
  synced_block: number;
}

export interface RequestDocument {
  request_id: string;
  title?: string;
  simulated?: boolean;
  target: { norad_id: number; name?: string };
  window: { start: string; end: string };
  requirements?: {
    min_observations?: number;
    max_angle_uncertainty_arcsec?: number;
  };
}

export interface OpenRequest {
  request_id: string;
  status: "open" | "funded";
  requester: string;
  request: RequestDocument;
  request_sha256: string;
  terms: {
    target_norad_id: number;
    window_start: string;
    window_end: string;
    delivery_deadline: string;
    reservation_hours: number;
    challenge_period_hours: number;
    review_hours: number;
    embargo_days: number;
    licence: string;
  };
  split: { observer: number; reviewer: number; platform_fee: number } | null;
  simulated: boolean;
}

/** The chain the service runs on, or null when it runs with the points ledger. */
export async function chainInfo(fetcher: typeof fetch = fetch): Promise<ChainInfo | null> {
  try {
    return await getJson<ChainInfo>("/v1/chain", fetcher);
  } catch (error) {
    if (error instanceof ApiError && error.code === "not_on_chain") return null;
    throw error;
  }
}

export interface Session {
  party: string;
  role: "requester" | "station" | "reviewer" | "admin";
  address: string;
  expires_at: string;
}

/** The signed-in party, or null. */
export async function currentSession(fetcher: typeof fetch = fetch): Promise<Session | null> {
  return (await getJson<{ session: Session | null }>("/v1/session", fetcher)).session;
}

export interface Target {
  norad_id: number;
  name: string | null;
}

export interface RequestListItem {
  request_id: string;
  requester: string;
  title: string | null;
  reserved_by: string | null;
  observer: string | null;
  status: string;
  outcome: string | null;
}

export interface Payout {
  party: string;
  points: number;
  reason: string;
}

export interface ChainEvent {
  event: string;
  at: string;
  block: number;
  tx_hash: string;
  explorer: string | null;
}

/** GET /v1/requests/{id}: the lifecycle record and what follows from it. */
export interface RequestView {
  summary: {
    request_id: string;
    status: string;
    outcome: string | null;
    outcome_reason: string | null;
    automated_verdict: string | null;
    reviewers: string[];
    votes: [string, boolean][];
    settlement: { plan: { outcome: string; deposit: number; payouts: Payout[] } } | null;
  };
  record: {
    request_id: string;
    requester: string;
    status: string;
    terms: OpenRequest["terms"] & { verification_timeout_hours: number; request_sha256: string };
    split: {
      observer: number;
      reviewer: number;
      platform_fee: number;
      challenge_reserve: number;
      total: number;
    } | null;
    reserved_by: string | null;
    reservation_expires_at: string | null;
    observer: string | null;
    delivery_sha256: string | null;
    delivered_at: string | null;
    automated_verdict: string | null;
    report_sha256: string | null;
    challenge_deadline: string | null;
    challenger: string | null;
    challenge_reason: string | null;
    reviewers: string[];
    review_deadline: string | null;
    outcome: string | null;
    outcome_reason: string | null;
  };
  publication: { state: string; public_from: string | null; licence: string };
  chain?: { on_chain: boolean; status: string | null; events: ChainEvent[] };
}

/** A station profile (format orbit-watch/station-profile 1.0). */
export interface StationProfile {
  format: string;
  format_version: string;
  simulated: boolean;
  id: string;
  description: string;
  station: {
    id: string;
    name?: string;
    latitude_deg: number;
    longitude_deg: number;
    altitude_m: number;
    [field: string]: unknown;
  };
  angle_type: string;
  declared_angle_uncertainty_arcsec: number;
  declared_time_uncertainty_s: number;
  [field: string]: unknown;
}

export interface VerificationReport {
  verdict: string;
  summary: string;
  checks: { id: string; title: string; result: string; reason: string }[];
}
