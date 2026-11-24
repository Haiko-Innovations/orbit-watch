# Data sources

Orbit Watch public testnet service · version of 24 November 2026

The service carries SIMULATED data and real data side by side. Every object, reference orbit and observation says which it is, on its page and in its files. The money is testnet money of no value.

## SIMULATED

The service's own objects and their orbits, the instruments of the stations, the observations that simulated stations make, and the reviewers are SIMULATED. The Orbit Watch simulator makes them; they are not real observations.

## Real objects and their orbits

The real objects on the allow-list come from [CelesTrak](https://celestrak.org)'s public GP data: its groups `science`, `education`, `amateur` and `cubesat`, without the objects of its groups `military` and `radar`, and without names that suggest military, intelligence or government security payloads. An administrator may add an object, and says publicly why. The current reference orbits of real objects are CelesTrak's GP data too, fetched one object at a time, as CelesTrak's usage policy asks.

The allow-list also holds objects whose operators publish their orbits, from CelesTrak's [supplemental GP data](https://celestrak.org/NORAD/elements/supplemental/), which CelesTrak derives from the operators' own orbital data: AST SpaceMobile's, Amazon Leo's (formerly Project Kuiper), Eutelsat OneWeb's and Planet's satellites, NASA's International Space Station, the satellites of the International Laser Ranging Service's predictions, and Starlink satellites that an administrator adds with SpaceX's published ephemeris. The navigation satellites of GPS, GLONASS and BeiDou, and dual-use satellites, stay off the list. We thank CelesTrak and these operators for publishing their data.

Past reference orbits, for replays, come from the IAU CPS's [SatChecker](https://satchecker.readthedocs.io/en/latest/), which asks for this acknowledgement:

> This research made use of data and/or services provided by the International Astronomical Union Centre for the Protection of the Dark and Quiet Sky (IAU CPS) SatHub. The development of SatChecker has been supported by the National Science Foundation (NSF) under grant numbers: AST 2332735 and AST 2332736. SatChecker is hosted at the NSF NOIRLab. Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the NSF, IAU, NSF NOIRLab, SKAO, ESO, or any host or member institution of the IAU CPS.

The service names each reference orbit by its source, its epoch and its SHA-256. It does not republish the orbits themselves.

## Replayed observations

A replay delivers observations that their observers published in [SCORE](https://score.cps.iau.org), the IAU CPS's Satellite Constellation Observation Repository, under the [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/) licence. Each replay names its observers by their ORCID iDs, its source and its licence, on its page and in its files. Orbit Watch converted the observations to its own format and changed nothing else. A replay station run by the service delivers them; it is never their observer, and nobody is paid for someone else's work.

SCORE asks for this acknowledgement:

> This research made use of data and/or services provided by the International Astronomical Union Centre for the Protection of the Dark and Quiet Sky (IAU CPS) SatHub. The development of SCORE has been supported by the National Science Foundation (NSF) under grant number: AST 2332736. SCORE is hosted at the NSF NOIRLab.

and for this statement on any website or web service that uses SCORE data:

> Any opinions, findings, and conclusions or recommendations expressed in this material are those of the author(s) and do not necessarily reflect the views of the NSF NOIRLab, the SKAO, the IAU, or any host or member institution of the IAU CPS.

If you are one of these observers and want your observations taken out of the service, write to info@haikoinnovations.com with "Orbit Watch privacy" in the subject line.
