// What each part of a request is, by its source (decisions P5-09 and D-52): the request,
// its object, its reference orbit and its observations. SIMULATED is said of what is
// simulated, and of nothing else. Pure functions, unit tested.

import { formatUtc } from "./format";
import { strings } from "./strings";

const s = strings.labels;

/** The service's labels of a request (`labels` in its summary and lists). */
export interface Labels {
  request_simulated: boolean;
  object: {
    norad_id: number;
    name: string | null;
    simulated: boolean;
    source: "service" | "celestrak" | "administrator" | null;
    groups?: string[] | undefined;
    /** CelesTrak's SupGP sources with its operator's orbit (decision D-62). */
    operator_orbits?: string[] | undefined;
    reason?: string | undefined;
    added_at?: string | undefined;
    on_list: boolean;
  };
  reference_orbit: {
    source: "celestrak" | "satchecker" | "uploaded" | "service";
    source_name: string;
    simulated: boolean;
    epoch: string;
    element_set_sha256: string;
    /** True once a verification report names it; before that, the nearest so far. */
    final: boolean;
  } | null;
  observations: { kind: "simulated" | "replayed" | "station"; station: string } | null;
  replay: {
    station: string;
    observations_sha256: string;
    source: string;
    url?: string;
    licence: string;
    observers: string[];
  } | null;
}

export interface LabelLine {
  term: string;
  text: string;
  simulated: boolean;
  /** ORCID iDs of the observers, linked after the text. */
  observers?: string[];
}

/** An epoch as GP data gives it ("2026-11-01T00:00:00.000000", in UTC), shown in UTC. */
export function epochText(epoch: string): string {
  const match = /^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z?$/.exec(epoch);
  if (!match) return epoch;
  return formatUtc(`${match[1]}${(match[2] ?? "").slice(0, 4)}Z`);
}

/** What an object on the list is and why it is there, in a few words. */
export function objectText(object: Labels["object"]): string {
  if (object.simulated) return s.objectSimulated;
  if (!object.on_list) return s.objectOffList;
  const operators = object.operator_orbits ?? [];
  const groups = object.groups ?? [];
  if (object.source === "celestrak") {
    if (operators.length === 0) return s.objectFromGroups(groups);
    if (groups.length === 0) return s.objectFromOperator(operators);
    return s.objectFromGroups(groups) + s.whoseOperator(operators);
  }
  if (object.source === "administrator") {
    const reason = object.reason ?? "";
    return operators.length > 0
      ? s.objectAddedWithOperator(reason, operators)
      : s.objectAdded(reason);
  }
  return s.objectReal;
}

/** The lines of a request's labels: its object, reference orbit and observations. */
export function labelLines(labels: Labels): LabelLine[] {
  const lines: LabelLine[] = [
    { term: s.object, text: objectText(labels.object), simulated: labels.object.simulated },
  ];
  const orbit = labels.reference_orbit;
  lines.push(
    orbit === null
      ? { term: s.orbit, text: s.orbitNone, simulated: false }
      : {
          term: s.orbit,
          text: `${s.orbitText(orbit.source_name, epochText(orbit.epoch))}${
            orbit.final ? "" : ` ${s.orbitSoFar}`
          }`,
          simulated: orbit.simulated,
        },
  );
  const delivered = labels.observations;
  const replay = labels.replay;
  if (replay !== null) {
    lines.push({
      term: s.observations,
      text: s.replayed(replay.source, replay.licence),
      simulated: false,
      observers: replay.observers,
    });
    lines.push({
      term: s.replay,
      text: delivered === null ? s.replayWaits(replay.station) : s.replayBy(delivered.station),
      simulated: false,
    });
  } else if (delivered === null) {
    lines.push({
      term: s.observations,
      text: labels.request_simulated ? s.awaitedSimulated : s.awaitedReal,
      simulated: labels.request_simulated,
    });
  } else {
    lines.push({
      term: s.observations,
      text:
        delivered.kind === "simulated"
          ? s.simulatedBy(delivered.station)
          : s.stationBy(delivered.station),
      simulated: delivered.kind === "simulated",
    });
  }
  return lines;
}

/** Short tags for a list of requests: SIMULATED, a real object, a replay. */
export function labelTags(labels: Labels): { text: string; simulated: boolean }[] {
  const tags: { text: string; simulated: boolean }[] = [];
  if (labels.request_simulated) tags.push({ text: strings.simulated, simulated: true });
  if (!labels.object.simulated) tags.push({ text: s.realObjectTag, simulated: false });
  if (labels.replay !== null) tags.push({ text: s.replayTag, simulated: false });
  return tags;
}

/** The same lines for a review task, from its files: the request document, the
 * observation file and the report. A task names no request, on purpose (decision D-23),
 * so the service gives it no labels; what the files say is enough. */
export function fileLines(
  request: { simulated?: boolean; replay?: Labels["replay"] } | null,
  observations: Uint8Array | null,
  report: { reference_orbit?: { epoch?: string; source?: { service?: string } } } | null,
): LabelLine[] {
  const lines: LabelLine[] = [];
  const reference = report?.reference_orbit;
  if (reference?.epoch) {
    const name = reference.source?.service;
    lines.push({
      term: s.orbit,
      text: s.orbitText(name ?? s.ownCatalogue, epochText(reference.epoch)),
      simulated: name === undefined && request?.simulated === true,
    });
  }
  const file = observations ? fileFacts(observations) : null;
  if (request?.replay) {
    lines.push({
      term: s.observations,
      text: s.replayed(request.replay.source, request.replay.licence),
      simulated: false,
      observers: request.replay.observers,
    });
  } else if (file?.origin) {
    lines.push({
      term: s.observations,
      text: s.published(file.origin.name, file.origin.licence),
      simulated: false,
      observers: file.origin.observers,
    });
  } else if (file) {
    lines.push({
      term: s.observations,
      text: file.simulated ? s.simulatedFile : s.stationFile,
      simulated: file.simulated,
    });
  }
  return lines;
}

interface FileFacts {
  simulated: boolean;
  origin: { name: string; licence: string; observers: string[] } | null;
}

/** What an observation file says of itself: SIMULATED, or published by others. */
export function fileFacts(bytes: Uint8Array): FileFacts {
  const text = new TextDecoder().decode(bytes);
  try {
    const document = JSON.parse(text) as {
      simulated?: unknown;
      source?: { origin?: { name?: unknown; licence?: unknown; observers?: unknown } };
    };
    const origin = document.source?.origin;
    return {
      simulated: document.simulated === true,
      origin:
        origin && typeof origin.name === "string" && typeof origin.licence === "string"
          ? {
              name: origin.name,
              licence: origin.licence,
              observers: Array.isArray(origin.observers)
                ? origin.observers.filter((o): o is string => typeof o === "string")
                : [],
            }
          : null,
    };
  } catch {
    // IOD and CCSDS TDM: a TDM says SIMULATED in a comment (observation-format.md).
    return { simulated: /simulated\s*=\s*true/i.test(text.slice(0, 4096)), origin: null };
  }
}
