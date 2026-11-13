import { strings } from "../strings";
import type { Resource } from "../useResource";

/** Loading and failure states of a resource; ``children`` renders the value. */
export function Loaded<T>({
  resource,
  reload,
  children,
}: {
  resource: Resource<T>;
  reload: () => void;
  children: (value: T) => React.ReactNode;
}) {
  if (resource.state === "loading") {
    return (
      <p className="muted" aria-live="polite">
        {strings.loading}
      </p>
    );
  }
  if (resource.state === "failed") {
    return (
      <div className="problem" role="alert">
        <p>
          <strong>{strings.errorTitle}</strong>: {resource.error.message}
        </p>
        <button type="button" onClick={reload}>
          {strings.retry}
        </button>
      </div>
    );
  }
  return <>{children(resource.value)}</>;
}

/** A plain link, or the text alone when there is no address (a local chain). */
export function MaybeLink({ href, children }: { href: string | null; children: React.ReactNode }) {
  if (href === null) return <>{children}</>;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  );
}
