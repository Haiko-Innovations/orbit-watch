import { useCallback } from "react";
import { getJson, type VerificationReport } from "../api";
import { strings } from "../strings";
import { useResource } from "../useResource";
import { Loaded } from "./Status";

/** The automated verification's checks, with their reasons: why it passed or failed. */
export function Verification({ sha }: { sha: string }) {
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
