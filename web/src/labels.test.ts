import { describe, expect, it } from "vitest";
import { epochText, fileFacts, fileLines, type Labels, labelLines, labelTags } from "./labels";

const own: Labels = {
  request_simulated: true,
  object: {
    norad_id: 339001,
    name: "SIM-CUBESAT-A (SIMULATED)",
    simulated: true,
    source: "service",
    on_list: true,
  },
  reference_orbit: {
    source: "service",
    source_name: "the service's own catalogue",
    simulated: true,
    epoch: "2026-11-01T00:00:00.000000",
    element_set_sha256: "ab",
    final: false,
  },
  observations: null,
  replay: null,
};

const real: Labels = {
  request_simulated: true,
  object: {
    norad_id: 99015,
    name: "TEST SCIENCE",
    simulated: false,
    source: "celestrak",
    groups: ["science"],
    on_list: true,
  },
  reference_orbit: {
    source: "celestrak",
    source_name: "CelesTrak",
    simulated: false,
    epoch: "2026-11-01T00:00:00.000000",
    element_set_sha256: "cd",
    final: true,
  },
  observations: { kind: "simulated", station: "station:SIM-ESPOO" },
  replay: null,
};

const replay: Labels = {
  request_simulated: false,
  object: {
    norad_id: 58296,
    name: "PELICAN 3001",
    simulated: false,
    source: "administrator",
    reason: "Its operator is a company that images the Earth.",
    on_list: true,
  },
  reference_orbit: {
    source: "satchecker",
    source_name: "IAU CPS SatChecker",
    simulated: false,
    epoch: "2024-05-08T12:00:00.000000",
    element_set_sha256: "ef",
    final: true,
  },
  observations: { kind: "replayed", station: "station:replay" },
  replay: {
    station: "station:replay",
    observations_sha256: "12",
    source: "SCORE, the IAU CPS Satellite Constellation Observation Repository",
    licence: "CC-BY-4.0",
    observers: ["0000-0002-1825-0097"],
  },
};

describe("labelLines", () => {
  it("says SIMULATED of everything simulated", () => {
    const lines = labelLines(own);
    expect(lines.map((line) => line.simulated)).toEqual([true, true, true]);
    expect(lines[1]?.text).toBe(
      "the service's own catalogue, epoch 2026-11-01 00:00 UTC (the nearest so far; the verification report names the one it uses)",
    );
    expect(lines[2]?.text).toBe("SIMULATED observations, not delivered yet");
  });

  it("says SIMULATED of the observations only, for a real object", () => {
    const lines = labelLines(real);
    expect(lines.map((line) => [line.term, line.simulated])).toEqual([
      ["Object", false],
      ["Reference orbit", false],
      ["Observations", true],
    ]);
    expect(lines[0]?.text).toBe("a real object, in CelesTrak's group science");
    expect(lines[1]?.text).toBe("CelesTrak, epoch 2026-11-01 00:00 UTC");
    expect(lines[2]?.text).toBe("SIMULATED, delivered by station:SIM-ESPOO");
  });

  it("names a replay's source, licence and observers, and its replay station", () => {
    const lines = labelLines(replay);
    expect(lines.every((line) => !line.simulated)).toBe(true);
    expect(lines[0]?.text).toBe(
      "a real object, added by an administrator: Its operator is a company that images the Earth.",
    );
    expect(lines[2]?.observers).toEqual(["0000-0002-1825-0097"]);
    expect(lines[2]?.text).toContain("published in SCORE");
    expect(lines[3]?.text).toBe(
      "delivered by the replay station station:replay, which is not their observer",
    );
    const waiting = labelLines({ ...replay, observations: null });
    expect(waiting[3]?.text).toBe(
      "the replay station station:replay delivers them; it is not their observer",
    );
  });

  it("asks for real observations of a real object without saying SIMULATED", () => {
    const lines = labelLines({ ...real, request_simulated: false, observations: null });
    expect(lines[2]).toEqual({
      term: "Observations",
      text: "real observations, not delivered yet",
      simulated: false,
    });
  });
});

describe("labelTags", () => {
  it("gives SIMULATED, a real object and a replay", () => {
    expect(labelTags(own).map((tag) => tag.text)).toEqual(["SIMULATED"]);
    expect(labelTags(real).map((tag) => tag.text)).toEqual(["SIMULATED", "Real object"]);
    expect(labelTags(replay).map((tag) => tag.text)).toEqual(["Real object", "Replay"]);
  });
});

describe("epochText", () => {
  it("reads GP epochs as UTC", () => {
    expect(epochText("2026-11-01T18:30:00.123456")).toBe("2026-11-01 18:30 UTC");
    expect(epochText("2026-11-01T18:30:00Z")).toBe("2026-11-01 18:30 UTC");
    expect(epochText("not a time")).toBe("not a time");
  });
});

describe("fileLines", () => {
  const encode = (value: unknown) => new TextEncoder().encode(JSON.stringify(value));

  it("labels a task's files without naming its request", () => {
    const lines = fileLines({ simulated: true }, encode({ simulated: true }), {
      reference_orbit: { epoch: "2026-11-01T00:00:00.000000" },
    });
    expect(lines).toEqual([
      {
        term: "Reference orbit",
        text: "the service's own catalogue, epoch 2026-11-01 00:00 UTC",
        simulated: true,
      },
      { term: "Observations", text: "SIMULATED, as the file says", simulated: true },
    ]);
  });

  it("names the observers of published observations", () => {
    const file = encode({
      simulated: false,
      source: {
        origin: { name: "SCORE", licence: "CC-BY-4.0", observers: ["0000-0002-1825-0097"] },
      },
    });
    const lines = fileLines({ simulated: false }, file, {
      reference_orbit: { epoch: "2024-05-08T12:00:00", source: { service: "IAU CPS SatChecker" } },
    });
    expect(lines[0]?.text).toBe("IAU CPS SatChecker, epoch 2024-05-08 12:00 UTC");
    expect(lines[0]?.simulated).toBe(false);
    expect(lines[1]?.text).toBe("published in SCORE under CC-BY-4.0 by");
    expect(lines[1]?.observers).toEqual(["0000-0002-1825-0097"]);
  });
});

describe("fileFacts", () => {
  it("reads a TDM's SIMULATED comment", () => {
    const tdm = new TextEncoder().encode("CCSDS_TDM_VERS = 2.0\nCOMMENT SIMULATED = TRUE\n");
    expect(fileFacts(tdm)).toEqual({ simulated: true, origin: null });
  });
});
