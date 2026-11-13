import { useEffect, useId, useMemo, useState } from "react";
import { type Address, isAddressEqual } from "viem";
import { ApiError, type ChainInfo, type Session } from "../api";
import {
  type Described,
  describePrepared,
  type Expected,
  type Prepared,
  RefusedTransaction,
} from "../chain/describe";
import { report, sendWithWallet, type TransactionView } from "../chain/send";
import { shortHex } from "../format";
import { strings } from "../strings";
import { rememberedWallet, rememberWallet } from "../wallet/current";
import { discoverWallets, type Wallet } from "../wallet/discovery";
import { connect, WalletError } from "../wallet/wallet";
import { MaybeLink } from "./Status";

// One flow for every prepared transaction (phase 3, step 3.3): what it does, read from its
// call data; the party's own wallet signs and sends; the service hears the hash and waits
// for the chain; the result is shown with its explorer link.

const t = strings.tx;

type Progress = { index: number; state: "waiting" | "sent"; hash?: string };

function Outcome({ view }: { view: TransactionView }) {
  return (
    <span className={`tx-state tx-${view.status}`}>
      {strings.transactions.states[view.status]} ·{" "}
      <MaybeLink href={view.explorer}>
        <code>{shortHex(view.tx_hash)}</code>
      </MaybeLink>
    </span>
  );
}

export default function TransactionFlow({
  prepared,
  chain,
  session,
  onDone,
  onCancel,
  expected,
}: {
  prepared: Prepared;
  expected?: Expected;
  chain: ChainInfo;
  session: Session;
  onDone: () => void;
  onCancel: () => void;
}) {
  const headingId = useId();
  const [wallet, setWallet] = useState<Wallet | null>(rememberedWallet());
  const [found, setFound] = useState<Wallet[] | null>(null);
  const [views, setViews] = useState<TransactionView[]>([]);
  const [progress, setProgress] = useState<Progress | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const described = useMemo((): Described[] | RefusedTransaction => {
    try {
      return describePrepared(prepared, chain, session.address as Address, expected ?? {});
    } catch (error) {
      if (error instanceof RefusedTransaction) return error;
      throw error;
    }
  }, [prepared, chain, session.address, expected]);

  useEffect(() => (wallet === null ? discoverWallets(setFound) : undefined), [wallet]);

  if (described instanceof RefusedTransaction) {
    return (
      <div className="problem" role="alert">
        <p>
          <strong>{t.problem}</strong>: {described.message}
        </p>
        <button type="button" onClick={onCancel}>
          {t.cancel}
        </button>
      </div>
    );
  }

  const finished = views.length === described.length;
  const failed = views.find((view) => view.status === "failed");
  const pending = views.find((view) => view.status === "pending");

  async function send(chosen: Wallet, list: Described[]) {
    setBusy(true);
    setProblem(null);
    try {
      const account = await connect(chosen.provider);
      if (!isAddressEqual(account, session.address as Address)) {
        throw new WalletError("wrong_account", t.wrongAccount(account, session.address));
      }
      rememberWallet(chosen);
      for (let index = views.length; index < list.length; index++) {
        const item = list[index] as Described;
        setProgress({ index, state: "waiting" });
        const hash = await sendWithWallet(chosen.provider, account, item);
        setProgress({ index, state: "sent", hash });
        const view = await report(hash);
        setViews((done) => [...done, view]);
        if (view.status !== "confirmed") break; // the next would fail without this one
      }
      setProgress(null);
    } catch (error) {
      setProgress(null);
      setProblem(
        error instanceof WalletError || error instanceof ApiError ? error.message : String(error),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel" aria-labelledby={headingId}>
      <h2 id={headingId} tabIndex={-1}>
        {t.review}
      </h2>
      <p className="muted">{t.reviewIntro}</p>
      <ol className="tx-list">
        {described.map((item, index) => (
          <li key={`${item.to}:${item.transaction.data}`}>
            <strong>{item.title}</strong>
            {item.detail ? <span>{item.detail}</span> : null}
            <span className="muted">
              {item.contract} <code className="hex">{item.to}</code> ·{" "}
              <code>{item.functionName}</code>
            </span>
            {views[index] ? <Outcome view={views[index] as TransactionView} /> : null}
          </li>
        ))}
      </ol>
      <div role="status" aria-live="polite">
        {progress ? (
          <p>
            {progress.state === "waiting"
              ? t.waiting((described[progress.index] as Described).title)
              : t.sent((described[progress.index] as Described).title)}
          </p>
        ) : null}
        {finished && !failed && !pending ? <p className="ok">{t.done}</p> : null}
        {pending ? <p>{t.pendingNote}</p> : null}
      </div>
      {failed ? (
        <div className="problem" role="alert">
          <p>{t.failedOnChain(failed.error ?? failed.status)}</p>
        </div>
      ) : null}
      {problem ? (
        <div className="problem" role="alert">
          <p>
            <strong>{t.problem}</strong>: {problem}
          </p>
        </div>
      ) : null}
      {wallet === null && !finished ? (
        found === null ? (
          <p className="muted">{strings.signIn.searching}</p>
        ) : found.length === 0 ? (
          <p>{t.noWallet}</p>
        ) : (
          <div>
            <p>{t.chooseWallet(session.address)}</p>
            <ul className="wallets">
              {found.map((option) => (
                <li key={option.info.uuid}>
                  <button
                    type="button"
                    className="wallet-choice"
                    disabled={busy}
                    onClick={() => {
                      setWallet(option);
                      void send(option, described);
                    }}
                  >
                    {option.info.icon ? (
                      <img src={option.info.icon} alt="" width="28" height="28" />
                    ) : null}
                    <span>{option.info.name}</span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )
      ) : null}
      <div className="actions">
        {wallet !== null && !finished && !failed && !pending ? (
          <button type="button" disabled={busy} onClick={() => void send(wallet, described)}>
            {t.send}
          </button>
        ) : null}
        <button
          type="button"
          className={finished || failed || pending ? "" : "secondary"}
          disabled={busy}
          onClick={finished || failed || pending ? onDone : onCancel}
        >
          {finished || failed || pending ? t.close : t.cancel}
        </button>
      </div>
    </section>
  );
}
