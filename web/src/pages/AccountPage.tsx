import { useCallback, useState } from "react";
import { type ChainInfo, deleteJson, getJson, postJson, type Session } from "../api";
import type { Prepared } from "../chain/describe";
import type { TransactionView } from "../chain/send";
import { actionKey, SendFlow } from "../components/SendFlow";
import { Loaded, MaybeLink } from "../components/Status";
import { addressLink, formatAmount, formatUtc, shortHex } from "../format";
import { paths } from "../router";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.account;

interface Balance {
  address: string | null;
  balance: number | null;
  withdrawable: number | null;
  token: { symbol: string; decimals: number };
}

function BalanceSection({ session, chain }: { session: Session; chain: ChainInfo }) {
  const load = useCallback(
    () => getJson<Balance>(`/v1/balances/${encodeURIComponent(session.party)}`),
    [session.party],
  );
  const [balance, reloadBalance] = useResource(load);
  const loadTransactions = useCallback(
    async () =>
      (await getJson<{ transactions: TransactionView[] }>("/v1/transactions")).transactions,
    [],
  );
  const [transactions, reloadTransactions] = useResource(loadTransactions);
  const [prepared, setPrepared] = useState<Prepared | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function withdraw() {
    setProblem(null);
    try {
      setPrepared(
        await postJson<Prepared>("/v1/wallet/withdraw", {}, { idempotencyKey: actionKey() }),
      );
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    }
  }

  function closeFlow() {
    setPrepared(null);
    reloadBalance();
    reloadTransactions();
  }

  return (
    <>
      <h2>{strings.balance.title}</h2>
      <Loaded resource={balance} reload={reloadBalance}>
        {(value) =>
          value.address === null ? (
            <p>{strings.balance.noWallet}</p>
          ) : (
            <>
              <dl className="details">
                <dt>{strings.balance.inWallet}</dt>
                <dd>{formatAmount(value.balance ?? 0, value.token)}</dd>
                <dt>{strings.balance.owed}</dt>
                <dd>{formatAmount(value.withdrawable ?? 0, value.token)}</dd>
              </dl>
              {prepared ? (
                <SendFlow
                  prepared={prepared}
                  chain={chain}
                  session={session}
                  onDone={closeFlow}
                  onCancel={closeFlow}
                />
              ) : (value.withdrawable ?? 0) > 0 ? (
                <button type="button" onClick={() => void withdraw()}>
                  {strings.balance.withdraw(formatAmount(value.withdrawable ?? 0, value.token))}
                </button>
              ) : (
                <p className="muted">{strings.balance.nothing}</p>
              )}
              {problem ? (
                <p className="problem" role="alert">
                  {problem}
                </p>
              ) : null}
            </>
          )
        }
      </Loaded>
      <h2>{strings.transactions.title}</h2>
      <Loaded resource={transactions} reload={reloadTransactions}>
        {(list) =>
          list.length === 0 ? (
            <p className="muted">{strings.transactions.none}</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">{strings.transactions.action}</th>
                    <th scope="col">{strings.transactions.request}</th>
                    <th scope="col">{strings.transactions.status}</th>
                    <th scope="col">{strings.transactions.transaction}</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((view) => (
                    <tr key={view.tx_hash}>
                      <td>
                        <code>{view.action}</code>
                      </td>
                      <td>{view.request_id ?? "–"}</td>
                      <td className={`tx-${view.status}`}>
                        {strings.transactions.states[view.status]}
                      </td>
                      <td>
                        <MaybeLink href={view.explorer}>
                          <code>{shortHex(view.tx_hash)}</code>
                        </MaybeLink>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        }
      </Loaded>
    </>
  );
}

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
      <button type="button" className="secondary" onClick={signOut}>
        {s.signOut}
      </button>
      {problem ? (
        <p className="problem" role="alert">
          {problem}
        </p>
      ) : null}
      {chain ? <BalanceSection session={session} chain={chain} /> : null}
    </>
  );
}
