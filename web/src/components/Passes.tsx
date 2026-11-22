import { useCallback, useId } from "react";
import { ApiError, getJson } from "../api";
import { formatUtc } from "../format";
import { type PassList, passCells } from "../passes";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";
import { Loaded } from "./Status";

const s = strings.passes;

/** A station's visible passes for a request (decisions P5-12, D-58). */
export function Passes({ requestId }: { requestId: string }) {
  const titleId = useId();
  const load = useCallback(async (): Promise<PassList | null> => {
    try {
      return await getJson<PassList>(`/v1/requests/${encodeURIComponent(requestId)}/passes`);
    } catch (error) {
      if (error instanceof ApiError && error.code === "no_profile") return null;
      throw error;
    }
  }, [requestId]);
  const [loaded, reload] = useResource(load);
  return (
    <section aria-labelledby={titleId} data-testid="passes">
      <h2 id={titleId}>{s.title}</h2>
      <Loaded resource={loaded} reload={reload}>
        {(list) =>
          list === null ? (
            <p>
              {s.noProfile} <a href={paths.station}>{s.stationLink}</a>
            </p>
          ) : (
            <>
              <p className="muted">{s.intro(list.min_elevation_deg, list.dark_sky_deg)}</p>
              {list.passes.length === 0 ? (
                <p>{s.none}</p>
              ) : (
                <div className="table-wrap">
                  <table aria-labelledby={titleId}>
                    <thead>
                      <tr>
                        <th scope="col">{s.rise}</th>
                        <th scope="col">{s.highestHeading}</th>
                        <th scope="col">{s.set}</th>
                        <th scope="col">{s.visibleHeading}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.passes.map((pass) => {
                        const [rise, highest, set, visible] = passCells(pass);
                        return (
                          <tr key={pass.rise} className={pass.visible ? "visible-pass" : undefined}>
                            <td>{rise}</td>
                            <td>{highest}</td>
                            <td>{set}</td>
                            <td>{visible}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              {list.passes.length > 0 && !list.passes.some((pass) => pass.visible) ? (
                <p>{s.noneVisible}</p>
              ) : null}
              {list.window_cut ? (
                <p className="muted">{s.cut(formatUtc(list.window_end))}</p>
              ) : null}
            </>
          )
        }
      </Loaded>
    </section>
  );
}
