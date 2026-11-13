import { useEffect, useState } from "react";

/** A link that saves ``text`` as the file ``name``. The text never leaves the browser
 * again: the page made it from the service's answer. */
export function DownloadLink({
  text,
  name,
  type = "application/json",
  children,
}: {
  text: string;
  name: string;
  type?: string;
  children: React.ReactNode;
}) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const made = URL.createObjectURL(new Blob([text], { type }));
    setUrl(made);
    return () => URL.revokeObjectURL(made);
  }, [text, type]);
  if (url === null) return null;
  return (
    <a className="button-link" href={url} download={name}>
      {children}
    </a>
  );
}
