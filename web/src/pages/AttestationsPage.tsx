import { type Attestation, type AttestationList, type ChainInfo, getJson } from "../api";
import { Loaded, MaybeLink } from "../components/Status";
import { addressLink, formatUtc, shortHex } from "../format";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.attestations;

function loadAttestations(): Promise<AttestationList> {
  return getJson<AttestationList>("/v1/public/attestations");
}

function says(attestation: Attestation): string {
  if (attestation.kind === "result") return s.verdict(attestation.fields.verdict ?? "?");
  return s.vote(attestation.fields.approve === true);
}

/** The public attestation browser (step 3.7): no sign-in, chain data only. */
export function AttestationsPage({ chain }: { chain: ChainInfo | null }) {
  const [list, reload] = useResource(loadAttestations);
  const explorer = chain?.explorer ?? null;
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <Loaded resource={list} reload={reload}>
        {(value) => (
          <>
            {value.attestations.length === 0 ? (
              <p>{s.none}</p>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th scope="col">{s.when}</th>
                      <th scope="col">{s.kind}</th>
                      <th scope="col">{s.request}</th>
                      <th scope="col">{s.says}</th>
                      <th scope="col">{s.by}</th>
                      <th scope="col">{s.attestation}</th>
                      <th scope="col">{s.transaction}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {value.attestations.map((attestation) => (
                      <tr key={attestation.uid}>
                        <td>{formatUtc(attestation.at)}</td>
                        <td>{s.kinds[attestation.kind] ?? attestation.kind}</td>
                        <td>
                          <code>{attestation.request_id}</code>
                        </td>
                        <td>{says(attestation)}</td>
                        <td>
                          {attestation.by_service ? (
                            s.service
                          ) : (
                            <MaybeLink href={addressLink(explorer, attestation.attester)}>
                              <code>{shortHex(attestation.attester)}</code>
                            </MaybeLink>
                          )}
                        </td>
                        <td>
                          <MaybeLink href={attestation.eas_scan}>
                            <code>{shortHex(attestation.uid)}</code>
                          </MaybeLink>
                        </td>
                        <td>
                          <MaybeLink href={attestation.explorer}>
                            <code>{shortHex(attestation.tx_hash)}</code>
                          </MaybeLink>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {chain?.local ? <p className="muted">{s.noScan}</p> : null}
            <h2>{s.schemas}</h2>
            <dl className="details">
              <dt>{s.resultSchema}</dt>
              <dd>
                <code className="hex">{value.result_schema}</code>
              </dd>
              <dt>{s.voteSchema}</dt>
              <dd>
                <code className="hex">{value.vote_schema}</code>
              </dd>
              <dt>{s.eas}</dt>
              <dd>
                <MaybeLink href={addressLink(explorer, value.eas)}>
                  <code className="hex">{value.eas}</code>
                </MaybeLink>
              </dd>
            </dl>
          </>
        )}
      </Loaded>
    </>
  );
}
