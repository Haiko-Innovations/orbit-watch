# Security policy

## Reporting a vulnerability

Please report security problems privately, not in public issues:

- use GitHub's [private vulnerability reporting](https://github.com/Haiko-Innovations/orbit-watch/security/advisories/new), or
- email info@haikoinnovations.com with "Orbit Watch security" in the subject line.

We aim to acknowledge reports within a week. Please give us a reasonable time to
fix the problem before you disclose it publicly.

## Scope

Phase 0 is a local command-line tool. It moves no money and runs no servers.
Relevant reports include, for example, unsafe parsing of untrusted observation
files, dependency vulnerabilities and anything that could make simulated data
appear real or make verification results non-reproducible.

Later phases (API, testnet contracts) will extend this policy. Orbit Watch never
asks for seed phrases or private keys.
