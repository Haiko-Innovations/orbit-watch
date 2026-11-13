import { useCallback } from "react";
import { getJson, type RequestListItem, type Session } from "../api";
import { Loaded } from "../components/Status";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.myRequests;

export function MyRequestsPage({ session }: { session: Session }) {
  const load = useCallback(async () => {
    const all = (await getJson<{ requests: RequestListItem[] }>("/v1/requests")).requests;
    return all.filter((item) => item.requester === session.party).reverse();
  }, [session.party]);
  const [requests, reload] = useResource(load);
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <p>
        <a className="button-link" href={paths.newRequest}>
          {s.new}
        </a>
      </p>
      <Loaded resource={requests} reload={reload}>
        {(items) =>
          items.length === 0 ? (
            <p>{s.none}</p>
          ) : (
            <ul className="request-list">
              {items.map((item) => (
                <li key={item.request_id}>
                  <a href={paths.request(item.request_id)}>{item.title ?? item.request_id}</a>
                  <span className="muted">
                    <code>{item.request_id}</code> ·{" "}
                    {strings.request.status[item.status] ?? item.status}
                    {item.outcome ? ` · ${strings.request.outcome(item.outcome)}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )
        }
      </Loaded>
    </>
  );
}
