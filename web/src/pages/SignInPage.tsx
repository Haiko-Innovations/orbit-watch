import { useEffect, useId, useRef, useState } from "react";
import type { Address } from "viem";
import { ApiError, type ChainInfo, postJson } from "../api";
import { paths } from "../router";
import { strings } from "../strings";
import { rememberWallet } from "../wallet/current";
import { discoverWallets, type Wallet } from "../wallet/discovery";
import { connect, signSignIn, switchToChain, WalletError } from "../wallet/wallet";

const s = strings.signIn;
const NAME = /^[A-Za-z0-9][A-Za-z0-9._-]{1,62}$/;

type Step =
  | { kind: "choose" }
  | { kind: "working"; text: string }
  | { kind: "sign-up"; wallet: Wallet; address: Address }
  | { kind: "failed"; text: string };

function WalletButton({ wallet, onChoose }: { wallet: Wallet; onChoose: () => void }) {
  return (
    <button type="button" className="wallet-choice" onClick={onChoose}>
      {wallet.info.icon ? <img src={wallet.info.icon} alt="" width="28" height="28" /> : null}
      <span>{wallet.info.name}</span>
    </button>
  );
}

function SignUpForm({
  address,
  onSubmit,
  onCancel,
}: {
  address: Address;
  onSubmit: (party: string) => void;
  onCancel: () => void;
}) {
  const [role, setRole] = useState<"requester" | "station">("station");
  const [name, setName] = useState("");
  const nameId = useId();
  const hintId = useId();
  const valid = NAME.test(name);
  const party = `${role}:${name}`;
  return (
    <form
      className="panel"
      onSubmit={(event) => {
        event.preventDefault();
        if (valid) onSubmit(party);
      }}
    >
      <h2 tabIndex={-1}>{s.signUpTitle}</h2>
      <p>{s.signUpIntro(address)}</p>
      <fieldset>
        <legend>{s.role}</legend>
        {(["requester", "station"] as const).map((value) => (
          <label key={value} className="choice">
            <input
              type="radio"
              name="role"
              value={value}
              checked={role === value}
              onChange={() => setRole(value)}
            />
            {s[value]}
          </label>
        ))}
      </fieldset>
      <label htmlFor={nameId}>{s.name}</label>
      <input
        id={nameId}
        value={name}
        onChange={(event) => setName(event.target.value.trim())}
        aria-describedby={hintId}
        aria-invalid={name !== "" && !valid}
        autoComplete="off"
        spellCheck={false}
        maxLength={63}
        required
      />
      <p id={hintId} className="muted">
        {s.nameHint}
      </p>
      {valid ? <p>{s.yourParty(party)}</p> : null}
      <div className="actions">
        <button type="submit" disabled={!valid}>
          {s.signUp}
        </button>
        <button type="button" className="secondary" onClick={onCancel}>
          {s.tryAgain}
        </button>
      </div>
      <p className="muted">{s.reviewersNote}</p>
    </form>
  );
}

export default function SignInPage({
  chain,
  onSignedIn,
}: {
  chain: ChainInfo | null;
  onSignedIn: () => void;
}) {
  const [wallets, setWallets] = useState<Wallet[] | null>(null);
  const [step, setStep] = useState<Step>({ kind: "choose" });
  const status = useRef<HTMLDivElement>(null);

  useEffect(() => discoverWallets(setWallets), []);
  // The sign-up form's heading takes the focus when it appears.
  useEffect(() => {
    if (step.kind === "sign-up") status.current?.querySelector<HTMLElement>("h2")?.focus();
  }, [step.kind]);

  if (chain === null) {
    return (
      <>
        <h1 tabIndex={-1}>{s.title}</h1>
        <p>{s.noChain}</p>
      </>
    );
  }

  async function start(wallet: Wallet, signUpParty?: string) {
    if (chain === null) return;
    try {
      setStep({ kind: "working", text: s.connecting(wallet.info.name) });
      const address = await connect(wallet.provider);
      setStep({ kind: "working", text: s.switching(chain.network) });
      await switchToChain(wallet.provider, chain.chain_id);
      let asked: { message: string };
      try {
        asked = await postJson<{ message: string }>(
          "/v1/session/challenge",
          signUpParty ? { address, sign_up: { party: signUpParty } } : { address },
        );
      } catch (error) {
        if (error instanceof ApiError && error.code === "unknown_wallet") {
          setStep({ kind: "sign-up", wallet, address });
          return;
        }
        throw error;
      }
      setStep({ kind: "working", text: s.confirm });
      const signature = await signSignIn(wallet.provider, address, asked.message);
      setStep({ kind: "working", text: s.checking });
      await postJson("/v1/session", { message: asked.message, signature });
      rememberWallet(wallet);
      onSignedIn();
      window.location.hash = paths.account;
    } catch (error) {
      const text =
        error instanceof WalletError || error instanceof ApiError ? error.message : String(error);
      setStep({ kind: "failed", text });
    }
  }

  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <div ref={status}>
        {step.kind === "choose" ? (
          <section className="panel" aria-labelledby="choose-wallet">
            <h2 id="choose-wallet">{s.chooseWallet}</h2>
            {wallets === null ? (
              <p className="muted" aria-live="polite">
                {s.searching}
              </p>
            ) : wallets.length === 0 ? (
              <p>{s.noWallet}</p>
            ) : (
              <ul className="wallets">
                {wallets.map((wallet) => (
                  <li key={wallet.info.uuid}>
                    <WalletButton wallet={wallet} onChoose={() => start(wallet)} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        ) : null}
        {step.kind === "working" ? (
          <p className="panel" role="status">
            {step.text}
          </p>
        ) : null}
        {step.kind === "sign-up" ? (
          <SignUpForm
            address={step.address}
            onSubmit={(party) => start(step.wallet, party)}
            onCancel={() => setStep({ kind: "choose" })}
          />
        ) : null}
        {step.kind === "failed" ? (
          <div className="problem" role="alert">
            <p>
              <strong>{s.failed}</strong>: {step.text}
            </p>
            <button type="button" onClick={() => setStep({ kind: "choose" })}>
              {s.tryAgain}
            </button>
          </div>
        ) : null}
      </div>
    </>
  );
}
