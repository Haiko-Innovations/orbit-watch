import { useCallback } from "react";
import { getJson, type ReviewerProfile, type ReviewTask, type Session } from "../api";
import { Loaded } from "../components/Status";
import { formatUtc } from "../format";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.tasks;

export async function loadTasks(): Promise<ReviewTask[]> {
  return (await getJson<{ tasks: ReviewTask[] }>("/v1/tasks")).tasks;
}

function ReviewerRecord({ party }: { party: string }) {
  const load = useCallback(
    () => getJson<ReviewerProfile>(`/v1/reviewers/${encodeURIComponent(party)}/profile`),
    [party],
  );
  const [profile, reload] = useResource(load);
  return (
    <Loaded resource={profile} reload={reload}>
      {(value) => (
        <>
          <dl className="details">
            <dt>{s.calibration}</dt>
            <dd>
              {s.calibrationLine(
                value.calibration.answered,
                value.calibration.correct,
                value.calibration.accuracy,
              )}
            </dd>
            <dt>{s.votes}</dt>
            <dd>
              {s.votesLine(
                value.votes.real_rounds,
                value.votes.total,
                value.votes.approval_rate,
                value.votes.agreed_with_outcome,
                value.votes.decided_rounds,
              )}
            </dd>
            {value.flags.length > 0 ? (
              <>
                <dt>{s.flags}</dt>
                <dd>
                  {value.flags.map((flag) => (
                    <p key={flag}>{s.flagText[flag] ?? flag}</p>
                  ))}
                </dd>
              </>
            ) : null}
          </dl>
          <p className="muted">
            {s.rewards} <a href={paths.account}>{strings.account.title}</a>
          </p>
        </>
      )}
    </Loaded>
  );
}

export function TasksPage({ session }: { session: Session }) {
  const [tasks, reload] = useResource(loadTasks);
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <Loaded resource={tasks} reload={reload}>
        {(items) =>
          items.length === 0 ? (
            <p>{s.none}</p>
          ) : (
            <ul className="request-list">
              {items.map((task) => (
                <li key={task.task_id} className="card">
                  <a href={paths.task(task.task_id)}>
                    {s.open}: <code>{task.task_id}</code>
                  </a>
                  <span>{s.due(formatUtc(task.due))}</span>
                  <span className="muted">{s.verdict(task.automated_verdict)}</span>
                  <span className="muted">
                    {s.challenge}: {task.challenge_reason}
                  </span>
                </li>
              ))}
            </ul>
          )
        }
      </Loaded>
      <h2>{s.record}</h2>
      <ReviewerRecord party={session.party} />
    </>
  );
}
