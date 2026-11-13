import { type ComponentProps, lazy, Suspense } from "react";
import { strings } from "../strings";

// The transaction flow with the wallet code (viem), loaded only when something is to be sent.
const TransactionFlow = lazy(() => import("./TransactionFlow"));

export function SendFlow(props: ComponentProps<typeof TransactionFlow>) {
  return (
    <Suspense fallback={<p className="muted">{strings.loading}</p>}>
      <TransactionFlow {...props} />
    </Suspense>
  );
}

/** A fresh Idempotency-Key for one action of the user (one click, one change). */
export function actionKey(): string {
  return crypto.randomUUID();
}
