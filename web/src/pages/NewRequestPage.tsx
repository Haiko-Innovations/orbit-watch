import { useId, useState } from "react";
import { ApiError, getJson, postJson, type Target } from "../api";
import { actionKey } from "../components/SendFlow";
import { Loaded } from "../components/Status";
import { inputFromUtc, utcFromInput } from "../format";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.newRequest;
const REQUEST_ID = /^[A-Za-z0-9._-]{1,64}$/;

interface Targets {
  targets: Target[];
  simulated: boolean;
}

async function loadTargets(): Promise<Targets> {
  return getJson<Targets>("/v1/public/targets");
}

/** A new request ID nobody else is likely to have chosen: the date and random letters. */
export function suggestRequestId(now: Date = new Date()): string {
  const day = now.toISOString().slice(0, 10).replaceAll("-", "");
  const letters = Array.from(crypto.getRandomValues(new Uint8Array(4)), (b) =>
    "ABCDEFGHJKLMNPQRSTUVWXYZ23456789".charAt(b % 32),
  ).join("");
  return `REQ-${day}-${letters}`;
}

function hoursFrom(now: Date, hours: number): string {
  return inputFromUtc(new Date(now.getTime() + hours * 3_600_000).toISOString());
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: (id: string, hintId: string | undefined) => React.ReactNode;
}) {
  const id = useId();
  const hintId = useId();
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {children(id, hint ? hintId : undefined)}
      {hint ? (
        <p id={hintId} className="muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

function RequestForm({ targets }: { targets: Targets }) {
  const now = new Date();
  const [form, setForm] = useState({
    requestId: suggestRequestId(now),
    title: "",
    target: String(targets.targets[0]?.norad_id ?? ""),
    windowStart: hoursFrom(now, 24),
    windowEnd: hoursFrom(now, 36),
    deadline: hoursFrom(now, 72),
    minObservations: "6",
    maxAngle: "60",
    maxTime: "0.1",
    radec: true,
    azel: true,
    reservationHours: "72",
    challengeHours: "24",
    reviewHours: "48",
    embargoDays: "0",
  });
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const set =
    (name: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm({
        ...form,
        [name]:
          event.target.type === "checkbox"
            ? (event.target as HTMLInputElement).checked
            : event.target.value,
      });

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setProblem(null);
    const start = utcFromInput(form.windowStart);
    const end = utcFromInput(form.windowEnd);
    const deadline = utcFromInput(form.deadline);
    const target = targets.targets.find((item) => String(item.norad_id) === form.target);
    const numbers = [
      form.minObservations,
      form.maxAngle,
      form.maxTime,
      form.reservationHours,
      form.challengeHours,
      form.reviewHours,
      form.embargoDays,
    ].map(Number);
    if (
      !REQUEST_ID.test(form.requestId) ||
      !form.title.trim() ||
      !target ||
      !start ||
      !end ||
      !deadline ||
      numbers.some((n) => !Number.isFinite(n) || n < 0) ||
      (!form.radec && !form.azel)
    ) {
      setProblem(s.invalid);
      return;
    }
    if (!(start < end && end < deadline)) {
      setProblem(s.windowOrder);
      return;
    }
    const document = {
      format: "orbit-watch/request",
      format_version: "1.0",
      simulated: targets.simulated,
      request_id: form.requestId,
      title: form.title.trim(),
      target: { norad_id: target.norad_id, ...(target.name ? { name: target.name } : {}) },
      window: { start, end },
      requirements: {
        min_observations: Number(form.minObservations),
        max_angle_uncertainty_arcsec: Number(form.maxAngle),
        max_time_uncertainty_s: Number(form.maxTime),
        angle_types: [...(form.radec ? ["radec"] : []), ...(form.azel ? ["azel"] : [])],
      },
    };
    const terms = {
      delivery_deadline: deadline,
      reservation_hours: Number(form.reservationHours),
      challenge_period_hours: Number(form.challengeHours),
      review_hours: Number(form.reviewHours),
      embargo_days: Number(form.embargoDays),
    };
    setBusy(true);
    try {
      await postJson("/v1/requests", { request: document, terms }, { idempotencyKey: actionKey() });
      window.location.hash = paths.request(form.requestId);
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel form" onSubmit={submit} noValidate>
      <Field label={s.requestId} hint={s.requestIdHint}>
        {(id, hint) => (
          <input
            id={id}
            value={form.requestId}
            onChange={set("requestId")}
            aria-describedby={hint}
            required
            maxLength={64}
            spellCheck={false}
          />
        )}
      </Field>
      <Field label={s.titleField}>
        {(id) => (
          <input id={id} value={form.title} onChange={set("title")} required maxLength={200} />
        )}
      </Field>
      <Field label={s.target} hint={s.targetHint}>
        {(id, hint) => (
          <select id={id} value={form.target} onChange={set("target")} aria-describedby={hint}>
            {targets.targets.map((target) => (
              <option key={target.norad_id} value={target.norad_id}>
                {target.name ?? "NORAD"} ({target.norad_id})
              </option>
            ))}
          </select>
        )}
      </Field>
      <div className="field-row">
        <Field label={s.windowStart}>
          {(id) => (
            <input
              id={id}
              type="datetime-local"
              value={form.windowStart}
              onChange={set("windowStart")}
              required
            />
          )}
        </Field>
        <Field label={s.windowEnd}>
          {(id) => (
            <input
              id={id}
              type="datetime-local"
              value={form.windowEnd}
              onChange={set("windowEnd")}
              required
            />
          )}
        </Field>
        <Field label={s.deadline}>
          {(id) => (
            <input
              id={id}
              type="datetime-local"
              value={form.deadline}
              onChange={set("deadline")}
              required
            />
          )}
        </Field>
      </div>
      <div className="field-row">
        <Field label={s.minObservations}>
          {(id) => (
            <input
              id={id}
              type="number"
              min="1"
              step="1"
              value={form.minObservations}
              onChange={set("minObservations")}
            />
          )}
        </Field>
        <Field label={s.maxAngle}>
          {(id) => (
            <input
              id={id}
              type="number"
              min="0"
              step="any"
              value={form.maxAngle}
              onChange={set("maxAngle")}
            />
          )}
        </Field>
        <Field label={s.maxTime}>
          {(id) => (
            <input
              id={id}
              type="number"
              min="0"
              step="any"
              value={form.maxTime}
              onChange={set("maxTime")}
            />
          )}
        </Field>
      </div>
      <fieldset>
        <legend>{s.angleTypes}</legend>
        <label className="choice">
          <input type="checkbox" checked={form.radec} onChange={set("radec")} /> {s.radec}
        </label>
        <label className="choice">
          <input type="checkbox" checked={form.azel} onChange={set("azel")} /> {s.azel}
        </label>
      </fieldset>
      <fieldset>
        <legend>{s.timing}</legend>
        <div className="field-row">
          <Field label={s.reservationHours}>
            {(id) => (
              <input
                id={id}
                type="number"
                min="0"
                step="any"
                value={form.reservationHours}
                onChange={set("reservationHours")}
              />
            )}
          </Field>
          <Field label={s.challengeHours}>
            {(id) => (
              <input
                id={id}
                type="number"
                min="0"
                step="any"
                value={form.challengeHours}
                onChange={set("challengeHours")}
              />
            )}
          </Field>
          <Field label={s.reviewHours}>
            {(id) => (
              <input
                id={id}
                type="number"
                min="0"
                step="any"
                value={form.reviewHours}
                onChange={set("reviewHours")}
              />
            )}
          </Field>
          <Field label={s.embargoDays}>
            {(id) => (
              <input
                id={id}
                type="number"
                min="0"
                max="30"
                step="1"
                value={form.embargoDays}
                onChange={set("embargoDays")}
              />
            )}
          </Field>
        </div>
      </fieldset>
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {s.create}
        </button>
      </div>
    </form>
  );
}

export function NewRequestPage() {
  const [targets, reload] = useResource(loadTargets);
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <Loaded resource={targets} reload={reload}>
        {(value) => <RequestForm targets={value} />}
      </Loaded>
    </>
  );
}
