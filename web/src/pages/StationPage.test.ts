import { describe, expect, it } from "vitest";
import type { StationProfile } from "../api";
import { stationProfile } from "./StationPage";

const template: StationProfile = {
  format: "orbit-watch/station-profile",
  format_version: "1.0",
  simulated: true,
  id: "sim-cmos-gps",
  description: "SIMULATED: CMOS camera with a wide lens and GPS (PPS) timing.",
  station: {
    id: "SIM-ESPOO",
    name: "Simulated station near Espoo, Finland",
    latitude_deg: 60.205,
    longitude_deg: 24.655,
    altitude_m: 40,
    iod_station_number: 9901,
  },
  angle_type: "radec",
  declared_angle_uncertainty_arcsec: 10,
  declared_time_uncertainty_s: 0.01,
};

describe("stationProfile", () => {
  it("keeps the instrument and puts in the station's own name and place", () => {
    const profile = stationProfile(template, "station:SIM-OBS-TEST", {
      name: "Test station",
      latitude: 61.5,
      longitude: 23.75,
      altitude: 110,
    });
    expect(profile.simulated).toBe(true);
    expect(profile.angle_type).toBe("radec");
    expect(profile.description).toBe(
      "SIMULATED: CMOS camera with a wide lens and GPS (PPS) timing.",
    );
    expect(profile.station).toEqual({
      id: "SIM-OBS-TEST",
      name: "Test station",
      latitude_deg: 61.5,
      longitude_deg: 23.75,
      altitude_m: 110,
    });
    expect(profile.id).toBe("sim-obs-test-sim-cmos-gps");
  });
});
