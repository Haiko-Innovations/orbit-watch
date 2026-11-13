import { useCallback, useId, useState } from "react";
import {
  ApiError,
  type ChainInfo,
  getJson,
  postJson,
  type RequestDocument,
  type ReviewTask,
  type Session,
} from "../api";
import type { Prepared } from "../chain/describe";
import { actionKey, SendFlow } from "../components/SendFlow";
import { Loaded } from "../components/Status";
import { Verification } from "../components/Verification";
import { formatUtc, shortHex } from "../format";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";
import { loadTasks } from "./TasksPage";

const s = strings.task;

interface TaskData {
  task: ReviewTask | null;
  request: RequestDocument | null;
}

async function sha256Text(text: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

function AnswerForm({
  task,
  chain,
  session,
}: {
  task: ReviewTask;
  chain: ChainInfo;
  session: Session;
}) {
  const ids = { title: useId(), reason: useId() };
  const [approve, setApprove] = useState<boolean | null>(null);
  const [reason, setReason] = useState("");
  const [prepared, setPrepared] = useState<{ prepared: Prepared; reasonSha256: string } | null>(
    null,
  );
  const [done, setDone] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (done) {
    return (
      <div className="panel" role="status">
        <p className="ok">{s.recorded}</p>
        <a href={paths.tasks}>{s.back}</a>
      </div>
    );
  }
  if (prepared && approve !== null) {
    return (
      <SendFlow
        prepared={prepared.prepared}
        chain={chain}
        session={session}
        expected={{
          vote: {
            approve,
            reasonSha256: prepared.reasonSha256,
            deliverySha256: task.observations_sha256,
          },
        }}
        onDone={() => {
          setPrepared(null);
          setDone(true);
        }}
        onCancel={() => setPrepared(null)}
      />
    );
  }

  async function answer(event: React.FormEvent) {
    event.preventDefault();
    if (approve === null || !reason.trim()) return;
    setBusy(true);
    setProblem(null);
    try {
      const text = reason.trim();
      const answered = await postJson<Prepared | Record<string, unknown>>(
        `/v1/tasks/${encodeURIComponent(task.task_id)}/review`,
        { approve, reason: text },
        { idempotencyKey: actionKey() },
      );
      // A vote in a real round is the reviewer's own attestation, signed in the wallet; a
      // calibration answer needs no transaction (decision D-23).
      if ("sign" in answered) {
        setPrepared({ prepared: answered as Prepared, reasonSha256: await sha256Text(text) });
      } else {
        setDone(true);
      }
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={answer} aria-labelledby={ids.title}>
      <h2 id={ids.title}>{s.formTitle}</h2>
      <p className="muted">{s.formIntro}</p>
      <fieldset>
        <legend>{s.choice}</legend>
        <label className="choice">
          <input
            type="radio"
            name="vote"
            checked={approve === true}
            onChange={() => setApprove(true)}
          />
          {s.approve}
        </label>
        <label className="choice">
          <input
            type="radio"
            name="vote"
            checked={approve === false}
            onChange={() => setApprove(false)}
          />
          {s.reject}
        </label>
      </fieldset>
      <label htmlFor={ids.reason}>{s.reason}</label>
      <textarea
        id={ids.reason}
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
        <button type="submit" disabled={busy || approve === null || !reason.trim()}>
          {s.prepare}
        </button>
      </div>
    </form>
  );
}

export function TaskPage({
  id,
  chain,
  session,
}: {
  id: string;
  chain: ChainInfo;
  session: Session;
}) {
  const load = useCallback(async (): Promise<TaskData> => {
    const task = (await loadTasks()).find((item) => item.task_id === id) ?? null;
    if (task === null) return { task, request: null };
    const request = await getJson<RequestDocument>(`/v1/files/${task.request_sha256}`);
    return { task, request };
  }, [id]);
  const [loaded, reload] = useResource(load);
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <Loaded resource={loaded} reload={reload}>
        {({ task, request }) =>
          task === null || request === null ? (
            <p>
              {s.notFound} <a href={paths.tasks}>{s.back}</a>
            </p>
          ) : (
            <>
              <p className="card-meta">
                <code>{task.task_id}</code> · {strings.tasks.due(formatUtc(task.due))}
              </p>
              <h2>{s.request}</h2>
              <dl className="details">
                <dt>{strings.newRequest.titleField}</dt>
                <dd>
                  {request.title ?? "–"}
                  {request.simulated ? (
                    <>
                      {" "}
                      <span className="badge">{strings.simulated}</span>
                    </>
                  ) : null}
                </dd>
                <dt>{strings.request.target}</dt>
                <dd>
                  {request.target.name ?? "NORAD"}{" "}
                  <span className="muted">({request.target.norad_id})</span>
                </dd>
                <dt>{strings.request.window}</dt>
                <dd>
                  {formatUtc(request.window.start)} – {formatUtc(request.window.end)}
                </dd>
              </dl>
              <h2>{s.challenge}</h2>
              <p>{task.challenge_reason}</p>
              <h2>{s.files}</h2>
              <ul className="file-list">
                <li>
                  <a
                    href={`/v1/files/${task.request_sha256}`}
                    download={`${task.task_id}-request.json`}
                  >
                    {strings.request.requestFile}
                  </a>{" "}
                  <code className="muted">{shortHex(task.request_sha256)}</code>
                </li>
                <li>
                  <a
                    href={`/v1/files/${task.observations_sha256}`}
                    download={`${task.task_id}-observations`}
                  >
                    {strings.request.observations}
                  </a>{" "}
                  <code className="muted">{shortHex(task.observations_sha256)}</code>
                </li>
                <li>
                  <a
                    href={`/v1/files/${task.report_sha256}`}
                    download={`${task.task_id}-report.json`}
                  >
                    {strings.request.report}
                  </a>{" "}
                  <code className="muted">{shortHex(task.report_sha256)}</code>
                </li>
              </ul>
              <Verification sha={task.report_sha256} />
              <AnswerForm task={task} chain={chain} session={session} />
            </>
          )
        }
      </Loaded>
    </>
  );
}
