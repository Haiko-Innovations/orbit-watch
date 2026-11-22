import { Fragment } from "react";
import { type LabelLine, type Labels, labelLines, labelTags } from "../labels";
import { strings } from "../strings";

/** The observers' ORCID iDs, each linked to its record. */
function Observers({ ids }: { ids: string[] }) {
  return (
    <>
      {ids.map((id, index) => (
        <span key={id}>
          {index > 0 ? ", " : " "}
          <a href={`https://orcid.org/${id}`} rel="noreferrer">
            {id}
          </a>
        </span>
      ))}
    </>
  );
}

/** Lines that say what each part is (decisions P5-09, D-52), as a definition list. */
export function LabelList({
  lines,
  title = true,
}: {
  lines: LabelLine[];
  title?: boolean | undefined;
}) {
  if (lines.length === 0) return null;
  return (
    <section className="labels" aria-label={strings.labels.title} data-testid="labels">
      {title ? <h2>{strings.labels.title}</h2> : null}
      <dl className="details compact">
        {lines.map((line) => (
          <Fragment key={line.term}>
            <dt>{line.term}</dt>
            <dd>
              {line.simulated ? (
                <>
                  <span className="badge">{strings.simulated}</span>{" "}
                </>
              ) : null}
              {line.text}
              {line.observers ? <Observers ids={line.observers} /> : null}
            </dd>
          </Fragment>
        ))}
      </dl>
    </section>
  );
}

/** A request's labels from the service. */
export function RequestLabels({
  labels,
  title,
}: {
  labels?: Labels | undefined;
  title?: boolean | undefined;
}) {
  return labels ? <LabelList lines={labelLines(labels)} title={title} /> : null;
}

/** Short tags for a request in a list: SIMULATED, a real object, a replay. */
export function LabelTags({ labels }: { labels?: Labels | undefined }) {
  if (!labels) return null;
  return (
    <span className="label-tags" data-testid="label-tags">
      {labelTags(labels).map((tag) => (
        <span key={tag.text} className={tag.simulated ? "badge" : "tag"}>
          {tag.text}
        </span>
      ))}
    </span>
  );
}
