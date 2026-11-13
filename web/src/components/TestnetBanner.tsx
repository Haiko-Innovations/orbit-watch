import { strings } from "../strings";

/** On every page (decision P3-09): the chain's own notice once it is known. */
export function TestnetBanner({ notice }: { notice: string | null }) {
  return (
    <div className="testnet-banner" role="note" data-testid="testnet-label">
      <strong>{notice ?? strings.testnetOnly}</strong>
      <span className="testnet-banner-detail">{strings.simulatedNote}</span>
    </div>
  );
}
