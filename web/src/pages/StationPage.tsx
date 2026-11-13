import { useCallback, useId, useState } from "react";
import { ApiError, getJson, putJson, type Session, type StationProfile } from "../api";
import { actionKey } from "../components/SendFlow";
import { Loaded } from "../components/Status";
import { strings } from "../strings";
import { useResource } from "../useResource";

const s = strings.station;

interface StationData {
  templates: StationProfile[];
  current: StationProfile | null;
}

/** The profile a station saves: a SIMULATED template, with the station's own name and place. */
export function stationProfile(
  template: StationProfile,
  party: string,
  place: { name: string; latitude: number; longitude: number; altitude: number },
): StationProfile {
  const id = party.split(":", 2)[1] ?? party;
  const { iod_station_number: _iod, ...station } = template.station;
  return {
    ...template,
    simulated: true,
    id: `${id.toLowerCase()}-${template.id}`.slice(0, 64),
    description: `SIMULATED: ${template.description.replace(/^SIMULATED:\s*/, "")}`,
    station: {
      ...station,
      id,
      name: place.name,
      latitude_deg: place.latitude,
      longitude_deg: place.longitude,
      altitude_m: place.altitude,
    },
  };
}

function ProfileForm({
  session,
  templates,
  current,
  onSaved,
}: {
  session: Session;
  templates: StationProfile[];
  current: StationProfile | null;
  onSaved: (profile: StationProfile) => void;
}) {
  const ids = {
    template: useId(),
    name: useId(),
    lat: useId(),
    lon: useId(),
    alt: useId(),
    hint: useId(),
  };
  const first = templates[0];
  const startFrom = templates.find((t) => current?.id.endsWith(t.id)) ?? first;
  const [templateId, setTemplateId] = useState(startFrom?.id ?? "");
  const base = current?.station ?? startFrom?.station;
  const [name, setName] = useState(String(base?.name ?? ""));
  const [latitude, setLatitude] = useState(String(base?.latitude_deg ?? ""));
  const [longitude, setLongitude] = useState(String(base?.longitude_deg ?? ""));
  const [altitude, setAltitude] = useState(String(base?.altitude_m ?? "0"));
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const template = templates.find((t) => t.id === templateId);

  /** A new station starts from the template's place too; a saved one keeps its own. */
  function choose(id: string) {
    setTemplateId(id);
    const next = templates.find((t) => t.id === id)?.station;
    if (current === null && next) {
      setName(String(next.name ?? ""));
      setLatitude(String(next.latitude_deg));
      setLongitude(String(next.longitude_deg));
      setAltitude(String(next.altitude_m));
    }
  }

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const place = {
      name: name.trim(),
      latitude: Number(latitude),
      longitude: Number(longitude),
      altitude: Number(altitude),
    };
    if (
      !template ||
      !place.name ||
      !(Math.abs(place.latitude) <= 90) ||
      !(Math.abs(place.longitude) <= 180) ||
      !Number.isFinite(place.altitude)
    ) {
      setMessage({ ok: false, text: s.invalid });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const saved = await putJson<{ profile: StationProfile }>(
        `/v1/stations/${encodeURIComponent(session.party)}/profile`,
        { profile: stationProfile(template, session.party, place) },
        actionKey(),
      );
      setMessage({ ok: true, text: s.saved });
      onSaved(saved.profile);
    } catch (error) {
      setMessage({ ok: false, text: error instanceof ApiError ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="panel" onSubmit={save} noValidate>
      <div className="field">
        <label htmlFor={ids.template}>{s.template}</label>
        <select
          id={ids.template}
          value={templateId}
          onChange={(e) => choose(e.target.value)}
          aria-describedby={ids.hint}
        >
          {templates.map((option) => (
            <option key={option.id} value={option.id}>
              {option.description.replace(/^SIMULATED:\s*/, "")}
            </option>
          ))}
        </select>
        <p id={ids.hint} className="muted">
          {s.templateHint}
        </p>
      </div>
      <div className="field">
        <label htmlFor={ids.name}>{s.name}</label>
        <input
          id={ids.name}
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={100}
        />
      </div>
      <div className="field-row">
        <div className="field">
          <label htmlFor={ids.lat}>{s.latitude}</label>
          <input
            id={ids.lat}
            inputMode="decimal"
            value={latitude}
            onChange={(e) => setLatitude(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.lon}>{s.longitude}</label>
          <input
            id={ids.lon}
            inputMode="decimal"
            value={longitude}
            onChange={(e) => setLongitude(e.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor={ids.alt}>{s.altitude}</label>
          <input
            id={ids.alt}
            inputMode="decimal"
            value={altitude}
            onChange={(e) => setAltitude(e.target.value)}
          />
        </div>
      </div>
      {message ? (
        <p className={message.ok ? "ok" : "problem"} role={message.ok ? "status" : "alert"}>
          {message.text}
        </p>
      ) : null}
      <div className="actions">
        <button type="submit" disabled={busy}>
          {s.save}
        </button>
      </div>
    </form>
  );
}

export function StationPage({ session }: { session: Session }) {
  const load = useCallback(async (): Promise<StationData> => {
    const { templates } = await getJson<{ templates: StationProfile[] }>(
      "/v1/public/station-templates",
    );
    try {
      const own = await getJson<{ profile: StationProfile }>(
        `/v1/stations/${encodeURIComponent(session.party)}/profile`,
      );
      return { templates, current: own.profile };
    } catch (error) {
      if (error instanceof ApiError && error.code === "no_profile")
        return { templates, current: null };
      throw error;
    }
  }, [session.party]);
  const [loaded, reload] = useResource(load);
  // A saved profile shows at once, without reloading the form (which keeps its message).
  const [saved, setSaved] = useState<StationProfile | null>(null);
  return (
    <>
      <h1 tabIndex={-1}>{s.title}</h1>
      <p className="lead">{s.intro}</p>
      <Loaded resource={loaded} reload={reload}>
        {({ templates, current: stored }) => {
          const current = saved ?? stored;
          return (
            <>
              {current ? (
                <dl className="details">
                  <dt>{s.stationId}</dt>
                  <dd>
                    <code>{current.station.id}</code>
                  </dd>
                  <dt>{s.name}</dt>
                  <dd>{current.station.name}</dd>
                  <dt>{s.latitude}</dt>
                  <dd>{current.station.latitude_deg}</dd>
                  <dt>{s.longitude}</dt>
                  <dd>{current.station.longitude_deg}</dd>
                  <dt>{s.instrument}</dt>
                  <dd>{current.description}</dd>
                </dl>
              ) : (
                <p>{s.none}</p>
              )}
              <ProfileForm
                session={session}
                templates={templates}
                current={current}
                onSaved={setSaved}
              />
            </>
          );
        }}
      </Loaded>
    </>
  );
}
