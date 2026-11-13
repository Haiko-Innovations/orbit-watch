import type { ChainInfo, Health } from "../api";
import { MaybeLink } from "../components/Status";
import { addressLink } from "../format";
import { strings } from "../strings";

const s = strings.network;

function Address({ explorer, value }: { explorer: string | null; value: string }) {
  return (
    <MaybeLink href={addressLink(explorer, value)}>
      <code className="hex">{value}</code>
    </MaybeLink>
  );
}

export function NetworkPage({ health, chain }: { health: Health; chain: ChainInfo | null }) {
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{chain ? s.intro : s.noChain}</p>
      <dl className="details">
        <dt>{s.service}</dt>
        <dd>{health.notice}</dd>
        <dt>{s.version}</dt>
        <dd>
          <code>{health.version}</code>
        </dd>
        {chain ? (
          <>
            <dt>{s.chain}</dt>
            <dd>
              {chain.network} <span className="muted">({chain.notice})</span>
            </dd>
            <dt>{s.chainId}</dt>
            <dd>
              <code>{chain.chain_id}</code>
            </dd>
            <dt>{s.escrow}</dt>
            <dd>
              <Address explorer={chain.explorer} value={chain.escrow} />
            </dd>
            <dt>{s.registry}</dt>
            <dd>
              <Address explorer={chain.explorer} value={chain.registry} />
            </dd>
            <dt>{s.token}</dt>
            <dd>
              {chain.token.symbol} <Address explorer={chain.explorer} value={chain.token.address} />
            </dd>
            <dt>{s.eas}</dt>
            <dd>
              <Address explorer={chain.explorer} value={chain.eas} />
            </dd>
            <dt>{s.resultSchema}</dt>
            <dd>
              <code className="hex">{chain.result_schema}</code>
            </dd>
            <dt>{s.voteSchema}</dt>
            <dd>
              <code className="hex">{chain.vote_schema}</code>
            </dd>
            <dt>{s.verifier}</dt>
            <dd>
              <Address explorer={chain.explorer} value={chain.verifier} />
            </dd>
            <dt>{s.feeRecipient}</dt>
            <dd>
              <Address explorer={chain.explorer} value={chain.fee_recipient} />
            </dd>
            <dt>{s.syncedBlock}</dt>
            <dd>
              <code>{chain.synced_block}</code>
            </dd>
            <dt>{s.explorer}</dt>
            <dd>
              {chain.explorer ? (
                <MaybeLink href={chain.explorer}>{chain.explorer}</MaybeLink>
              ) : (
                s.noExplorer
              )}
            </dd>
          </>
        ) : null}
      </dl>
    </>
  );
}
