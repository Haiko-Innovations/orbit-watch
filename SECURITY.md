# Security policy

## Reporting a vulnerability

Please report security problems privately, not in public issues:

- use GitHub's [private vulnerability reporting](https://github.com/Haiko-Innovations/orbit-watch/security/advisories/new), or
- email info@haikoinnovations.com with "Orbit Watch security" in the subject line.

We aim to acknowledge reports within a week. Please give us a reasonable time to
fix the problem before you disclose it publicly.

## Scope

Orbit Watch runs a public testnet service: the API and the web application on
Base Sepolia, with no real value and SIMULATED data, as well as the command-line
tools and the testnet contracts. Relevant reports include, for example:

- reading or changing another party's data;
- flaws in signing in or in sessions;
- leaks of a secret, such as the verifier key, the database or a token;
- unsafe parsing of untrusted observation files;
- dependency vulnerabilities;
- anything that could make simulated data appear real, or make verification
  results non-reproducible.

Orbit Watch never asks for seed phrases or private keys.

## Dependencies and fixes

- **Updates.** Dependabot proposes ordinary updates every week, once a release is
  14 days old. Security updates come at once, without that wait.
- **Checks.** Every pull request fails when a runtime dependency has a known
  vulnerability (`pip-audit`, `npm audit`), so none can be merged with one.
- **Secrets.** GitHub's secret scanning with push protection is on, and gitleaks
  scans the whole history in CI.
- **Time to a fix.** From the time a vulnerability is known in Orbit Watch or a
  dependency it uses:

  | Severity | Fixed or mitigated within |
  |---|---|
  | Exploitable in the public service, or critical | 2 days; meanwhile [read-only mode](docs/operations.md#read-only-mode) if it helps |
  | High | 7 days |
  | Medium | 30 days |
  | Low | the next ordinary update |

The review before the launch, against OWASP ASVS level 1, is in
[docs/security-review.md](docs/security-review.md).
