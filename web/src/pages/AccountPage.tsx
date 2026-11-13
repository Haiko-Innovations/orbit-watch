import { useState } from "react";
import { type ChainInfo, deleteJson, type Session } from "../api";
import { MaybeLink } from "../components/Status";
import { addressLink, formatUtc } from "../format";
import { paths } from "../router";
import { strings } from "../strings";

const s = strings.account;

export function AccountPage({
  session,
  chain,
  onSignedOut,
}: {
  session: Session | null;
  chain: ChainInfo | null;
  onSignedOut: () => void;
}) {
  const [problem, setProblem] = useState<string | null>(null);
  if (session === null) {
    return (
      <>
        <h1 tabIndex={-1}>{s.title}</h1>
        <p>{s.notSignedIn}</p>
        <p>
          <a href={paths.signIn}>{strings.session.signIn}</a>
        </p>
      </>
    );
  }
  async function signOut() {
    try {
      await deleteJson("/v1/session");
      onSignedOut();
      window.location.hash = paths.network;
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    }
  }
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <dl className="details">
        <dt>{s.party}</dt>
        <dd>
          <code>{session.party}</code>
        </dd>
        <dt>{s.role}</dt>
        <dd>{s.roles[session.role]}</dd>
        <dt>{s.wallet}</dt>
        <dd>
          <MaybeLink href={addressLink(chain?.explorer ?? null, session.address)}>
            <code className="hex">{session.address}</code>
          </MaybeLink>
        </dd>
        <dt>{s.expires}</dt>
        <dd>{formatUtc(session.expires_at)}</dd>
      </dl>
      <button type="button" onClick={signOut}>
        {s.signOut}
      </button>
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
    </>
  );
}
