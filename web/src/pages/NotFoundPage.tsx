import { paths } from "../router";
import { strings } from "../strings";

export function NotFoundPage() {
  return (
    <>
      <h1 tabIndex={-1}>{strings.notFound.title}</h1>
      <p>{strings.notFound.body}</p>
      <p>
        <a href={paths.network}>{strings.notFound.home}</a>
      </p>
    </>
  );
}
