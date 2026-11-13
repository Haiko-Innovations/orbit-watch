import { useId, useState } from "react";
import { ApiError, postBytes, type QualityResult, type QualityRow } from "../api";
import { strings } from "../strings";

const s = strings.quality;

function number(value: number | null | undefined): string {
  return value === null || value === undefined ? "–" : String(value);
}

function Cells({ row }: { row: QualityRow }) {
  return (
    <>
      <td>{row.observations}</td>
      <td>{number(row.angle_scatter_arcsec)}</td>
      <td>{number(row.timing_scatter_s)}</td>
      <td>{number(row.mean_along_track_s)}</td>
    </>
  );
}

function Headings() {
  return (
    <>
      <th scope="col">{s.observations}</th>
      <th scope="col">{s.angle}</th>
      <th scope="col">{s.timing}</th>
      <th scope="col">{s.offset}</th>
    </>
  );
}

function Report({ result }: { result: QualityResult }) {
  const { report } = result;
  return (
    <section aria-labelledby="quality-result">
      <h2 id="quality-result">
        {s.station}: {report.station.name ?? report.station.id}{" "}
        {report.simulated_input ? <span className="badge">{strings.simulated}</span> : null}
      </h2>
      {report.notice ? <p className="muted">{report.notice}</p> : null}
      <p>{report.summary}</p>
      {report.findings && report.findings.length > 0 ? (
        <>
          <h3>{s.findings}</h3>
          <ul>
            {report.findings.map((finding) => (
              <li key={finding}>{finding}</li>
            ))}
          </ul>
        </>
      ) : null}
      {report.overall ? (
        <dl className="details">
          <dt>{s.overall}</dt>
          <dd>{report.overall.observations}</dd>
          <dt>{s.angle}</dt>
          <dd>{number(report.overall.angle_scatter_arcsec)}</dd>
          <dt>{s.timing}</dt>
          <dd>{number(report.overall.timing_scatter_s)}</dd>
          <dt>{s.offset}</dt>
          <dd>{number(report.overall.mean_along_track_s)}</dd>
          <dt>{s.declaredAngle}</dt>
          <dd>{report.overall.declared_angle_uncertainty_arcsec.join(", ")}</dd>
          <dt>{s.declaredTime}</dt>
          <dd>{report.overall.declared_time_uncertainty_s.join(", ")}</dd>
        </dl>
      ) : null}
      {report.objects && report.objects.length > 0 ? (
        <>
          <h3>{s.objects}</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{s.object}</th>
                  <th scope="col">{s.passes}</th>
                  <th scope="col">{s.median}</th>
                  <Headings />
                </tr>
              </thead>
              <tbody>
                {report.objects.map((object) => (
                  <tr key={object.norad_id}>
                    <td>
                      {object.name ?? "NORAD"} ({object.norad_id})
                    </td>
                    <td>{object.passes}</td>
                    <td>{number(object.median_residual_arcsec)}</td>
                    <Cells row={object} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      {report.nights && report.nights.length > 0 ? (
        <>
          <h3>{s.nights}</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">{s.night}</th>
                  <Headings />
                </tr>
              </thead>
              <tbody>
                {report.nights.map((night) => (
                  <tr key={night.night}>
                    <td>{night.night}</td>
                    <Cells row={night} />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
      <h3>{s.notices}</h3>
      <ul>
        {report.notices.map((notice) => (
          <li key={notice}>{notice}</li>
        ))}
      </ul>
      {result.warnings.length + result.skipped.length > 0 ? (
        <>
          <h3>{s.warnings}</h3>
          <ul>
            {[...result.warnings, ...result.skipped].map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </>
      ) : null}
    </section>
  );
}

/** The public station quality meter (step 3.7): no sign-in; the file is not kept. */
export function QualityPage() {
  const ids = { file: useId(), format: useId() };
  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState("");
  const [result, setResult] = useState<QualityResult | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function measure(event: React.FormEvent) {
    event.preventDefault();
    if (file === null) return;
    setBusy(true);
    setProblem(null);
    setResult(null);
    try {
      const bytes = new Uint8Array(await file.arrayBuffer());
      const query = format ? `?format=${encodeURIComponent(format)}` : "";
      setResult(await postBytes<QualityResult>(`/v1/public/quality${query}`, bytes));
    } catch (error) {
      setProblem(error instanceof ApiError ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <form className="panel" onSubmit={measure}>
        <div className="field-row">
          <div className="field">
            <label htmlFor={ids.file}>{s.file}</label>
            <input
              id={ids.file}
              type="file"
              accept=".json,.iod,.txt,.tdm,.kvn"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </div>
          <div className="field">
            <label htmlFor={ids.format}>{s.format}</label>
            <select id={ids.format} value={format} onChange={(e) => setFormat(e.target.value)}>
              <option value="">{s.detect}</option>
              {Object.entries(strings.delivery.formats).map(([value, name]) => (
                <option key={value} value={value}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        </div>
        {problem ? (
          <p className="problem" role="alert">
            {problem}
          </p>
        ) : null}
        <div className="actions">
          <button type="submit" disabled={busy || file === null}>
            {busy ? s.measuring : s.measure}
          </button>
        </div>
      </form>
      {result ? <Report result={result} /> : null}
    </>
  );
}
