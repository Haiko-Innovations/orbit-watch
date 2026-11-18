# Security review before the launch

Phase 4, step 4.7 ([P4-14](decisions.md#p4-14-a-review-before-the-launch),
[D-40](decisions.md#d-40-the-review-before-the-launch)). The public testnet
service, its web application, its deployment and the repository, reviewed on
2026-11-17 against **every level 1 requirement of the OWASP Application Security
Verification Standard 5.0.0** ([ASVS](https://github.com/OWASP/ASVS/tree/v5.0.0_release/5.0/en),
released 2025-05-30). That is 65 requirements, a superset of P4-14's short list:
authentication, sessions, input, headers, limits, secrets and logging. Each
requirement was checked against the code and, where it applies, against the
running service at https://orbit-watch-tan.vercel.app.

> **Testnet only, no real value.** Everything the service holds is SIMULATED or
> on Base Sepolia.

**Result:** five findings were fixed and four were recorded as accepted. No
requirement is unmet.

| Status | Meaning |
|---|---|
| Pass | met, with the evidence named |
| Fixed | not met before the review, fixed with it (the findings below) |
| Accepted | not met to the letter, and why that is right here |
| N/A | does not apply: Orbit Watch has no such feature |

## Findings

| # | Requirement | Finding | Outcome |
|---|---|---|---|
| R1 | 3.3.1 | The session cookie `ow_session` had no `__Host-` prefix, so a cookie with that name could have come from elsewhere. | **Fixed.** Over HTTPS the cookie is `__Host-ow_session` (`Secure`, `Path=/`, no `Domain`), and a session signed in over HTTPS counts only under that name. Plain http on a developer's machine keeps `ow_session`. Tests: `test_sessions.py`. |
| R2 | 7.2.4 | Signing in again left the browser's earlier session alive. | **Fixed.** A sign-in ends the session that the browser had. Test: `test_sessions.py`. |
| R3 | 8.2.2 | Any signed-in party could read the reasons written for any request's challenge and votes, while the [data inventory](personal-data.md) says only its parties and the administrators see them. | **Fixed.** `GET /v1/requests/{id}` hides `challenge_reason` and `vote_reasons` from others until the request is published, and says `"reasons_hidden": true`. Test: `test_review.py`. |
| R4 | 15.1.1 | There were no time frames for fixing vulnerable dependencies, and `SECURITY.md` still described phase 0. | **Fixed.** [SECURITY.md](../SECURITY.md) gives time frames by severity (2 days to the next update) and the service's scope. |
| R5 | 15.2.1, secrets | GitHub's secret scanning, its push protection and Dependabot security updates were off, although `dependabot.yml` counts on security updates arriving at once. | **Fixed.** All three turned on 2026-11-17. No open alert. |
| R6 | 3.5.3 | `GET /v1/internal/follow` and `GET /v1/internal/backup` act on a `GET`. | **Accepted.** Vercel's cron jobs send `GET`. Both need a bearer token in a header, which a browser never adds by itself, so another site cannot trigger them. A backup changes nothing. |
| R7 | 7.2.2 | API keys are long-lived secrets. | **Accepted.** Browsers use sessions with fresh tokens. API keys are for command-line tools: 256 random bits, stored only as SHA-256. An administrator revokes them in the database (`api_keys.revoked`); the service has no command for it yet. |
| R8 | 7.4.2 | There is no way in the service to disable an account and end its sessions. | **Accepted.** Accounts are deleted by an administrator, on request, who now ends the party's sessions first ([personal-data.md](personal-data.md#requests-from-the-people-the-data-is-about)). A party ends its own sessions everywhere with `DELETE /v1/sessions`. |
| R9 | 6.2.1–6.2.8, 6.4.1–6.4.2 | — | **N/A.** There are no passwords: people sign in with a wallet signature (ERC-4361), and tools use API keys. |

## The requirements

### V1 Encoding and sanitization

| | Status | Evidence |
|---|---|---|
| 1.2.1 Output encoding | Pass | The API answers JSON, and stored files as `application/octet-stream` with `nosniff`. The web application renders text through React, which escapes it. Its Markdown reader makes React elements, never HTML (D-37). No `dangerouslySetInnerHTML`. |
| 1.2.2 URLs | Pass | Path parameters are encoded with `encodeURIComponent`. Markdown links may be only `https:`, `mailto:` or `#/` (`SAFE_HREF`). Explorer links come from the deployment record. |
| 1.2.3 JavaScript and JSON | Pass | JSON is built with `json.dumps` and `JSON.stringify`, never by hand. |
| 1.2.4 Database queries | Pass | Every value is a query parameter. Only names are composed into SQL: role names with `psycopg.sql.Identifier`, and backup tables after a check against the schema and a pattern. |
| 1.2.5 OS commands | Pass | The service runs no operating system commands. |
| 1.3.1 HTML from editors | N/A | No HTML input. |
| 1.3.2 `eval` | Pass | None in Python or the web application; the CSP does not allow `unsafe-eval`. |
| 1.5.1 XML parsers | N/A | No XML is parsed; TDM files are read in their KVN syntax. |

### V2 Validation and business logic

| | Status | Evidence |
|---|---|---|
| 2.1.1 Documented rules | Pass | JSON schemas in `core/src/orbit_watch/schemas`, [observation-format.md](observation-format.md), [api.md](api.md). |
| 2.2.1 Positive validation | Pass | Schemas, the target allow-list (D-05), limits on numbers and sizes. |
| 2.2.2 At the service | Pass | Every check runs in the service; the web application's checks only help. |
| 2.3.1 Steps in order | Pass | The lifecycle is a state machine; a step out of order is `forbidden_in_status` ([lifecycle.md](lifecycle.md)). On the chain, the escrow enforces the same order. |

### V3 Web frontend

| | Status | Evidence |
|---|---|---|
| 3.2.1 Wrong context | Pass | `X-Content-Type-Options: nosniff` and a strict CSP on every response. API answers are JSON, and files are `application/octet-stream`, so a browser never renders them. |
| 3.2.2 Text as text | Pass | React text nodes. |
| 3.3.1 Cookie prefix | Fixed | R1. |
| 3.4.1 HSTS | Pass | Vercel sends `Strict-Transport-Security: max-age=63072000; includeSubDomains; preload` on every response (checked on the API and the pages). |
| 3.4.2 CORS | Pass | The API sends no CORS headers: it is on the pages' own origin (D-25). |
| 3.5.1 Cross-origin requests | Pass | A change made with a session must carry the `Origin` of the page it was signed in on, and the cookie is `SameSite=Strict`. |
| 3.5.2 Preflight | N/A | Nothing relies on preflight; see 3.5.1. |
| 3.5.3 Safe methods | Accepted | R6. Every other change is `POST`, `PUT` or `DELETE`. |

### V4 API and web service

| | Status | Evidence |
|---|---|---|
| 4.1.1 Content-Type | Pass | `application/json`, which is UTF-8 by definition (RFC 8259), and `application/octet-stream` from the API. Pages are `text/html; charset=utf-8`. |
| 4.4.1 WebSockets | N/A | None. |

### V5 File handling

| | Status | Evidence |
|---|---|---|
| 5.2.1 Size | Pass | Bodies at most 4,000,000 bytes; the quality meter at most 2 MiB ([limits](api.md#limits-against-abuse)). |
| 5.2.2 Type | Pass | A delivered file is parsed in its declared format and refused if it does not parse; there are no file extensions. |
| 5.3.1 Not executed | Pass | Files are kept in the database by SHA-256 and served for download only. |
| 5.3.2 Paths | Pass | The service builds no file paths from what it receives. |

### V6 Authentication

| | Status | Evidence |
|---|---|---|
| 6.1.1 Documented defences | Pass | Sign-in and sign-up limits per IP address ([limits](api.md#limits-against-abuse)) and Vercel's firewall. |
| 6.2.1–6.2.8 Passwords | N/A | R9. |
| 6.3.1 Brute force | Pass | The limits above. A sign-in message works once, for 5 minutes. API keys and session tokens have 256 random bits. |
| 6.3.2 Default accounts | Pass | None. The first administrator key is made with `orbit-watch keys create`; the local stack's test keys never reach production. |
| 6.4.1 Initial secrets | N/A | No initial passwords. API keys are shown once. |
| 6.4.2 Hints | N/A | None. |

### V7 Session management

| | Status | Evidence |
|---|---|---|
| 7.2.1 Checked by the service | Pass | Sessions are rows in the database, looked up by the cookie's SHA-256. |
| 7.2.2 Dynamic tokens | Accepted | R7. |
| 7.2.3 128 bits from a CSPRNG | Pass | `secrets.token_urlsafe(32)`: 256 bits. |
| 7.2.4 New token at sign-in | Fixed | R2. |
| 7.4.1 Ended for good | Pass | Signing out deletes the session's row (step 4.4). |
| 7.4.2 Disabled accounts | Accepted | R8. |

### V8 Authorization

| | Status | Evidence |
|---|---|---|
| 8.1.1 Documented | Pass | Roles in [api.md](api.md#keys-and-roles), who sees what in [personal-data.md](personal-data.md). |
| 8.2.1 Function level | Pass | Every endpoint names its roles (`forbidden_role`). |
| 8.2.2 Data level | Fixed | R3. Reports and files were already restricted to the parties (`can_read_request_data`, `can_read_file`). |
| 8.3.1 At the service | Pass | All checks are in the service. |

### V9 Self-contained tokens

| | Status | Evidence |
|---|---|---|
| 9.1.1–9.2.1 | N/A | No self-contained tokens: sessions are references to rows. The sign-in message is checked against the service's own record of it, its signature, origin, address, chain and expiry (D-27). |

### V11 Cryptography

| | Status | Evidence |
|---|---|---|
| 11.3.1–11.3.2 Ciphers | Pass | TLS is Vercel's and Neon's. Backups use age: X25519 and ChaCha20-Poly1305 (D-39). |
| 11.4.1 Hashes | Pass | SHA-256 for files, keys and tokens, keyed SHA-256 for IP addresses, Keccak-256 on the chain. No MD5 or SHA-1. |

### V12 Secure communication

| | Status | Evidence |
|---|---|---|
| 12.1.1 TLS versions | Pass | The service refuses TLS 1.0 and 1.1 and offers 1.2 and 1.3 (checked with `openssl s_client`). |
| 12.2.1 TLS everywhere | Pass | `http://` answers `308` to `https://`. The database connection is `verify-full` (D-38), and the RPC endpoint is HTTPS. |
| 12.2.2 Trusted certificates | Pass | Vercel's publicly trusted certificate. |

### V13 Configuration

| | Status | Evidence |
|---|---|---|
| 13.4.1 No source control metadata | Pass | `/.git/config` and `/.git/HEAD` answer `404`; Vercel deploys no `.git`. |

### V14 Data protection

| | Status | Evidence |
|---|---|---|
| 14.2.1 Nothing sensitive in URLs | Pass | Keys and tokens travel in headers or the cookie, never in a query string. |
| 14.3.1 Client storage | Pass | The web application stores nothing in the browser. The cookie is `HttpOnly` and deleted at sign-out. |

### V15 Secure coding and architecture

| | Status | Evidence |
|---|---|---|
| 15.1.1 Time frames | Fixed | R4. |
| 15.2.1 Within them | Pass | CI fails on any known vulnerability in runtime dependencies; no Dependabot alert is open. R5 turned on the security updates. |
| 15.3.1 Only needed fields | Pass | Public answers carry summaries, not records. Station profiles go only to the station and the administrators. Wallet signatures go only to administrators. Since R3, reasons go only to the parties. |

### V16 Logging, and P4-14's other items

ASVS 5.0 has no level 1 requirement on logging; P4-14 asks for it.

- **Logging.** The service writes no IP address and no secret to its logs, which the
  tests check: database passwords, the verifier key and the RPC endpoint's key.
  A failed start logs why, without the setting's value. Errors answer with a code
  and a message, never a stack trace.
- **Limits:** [D-36](decisions.md#d-36-limits-the-body-limit-and-the-dedicated-rpc-endpoint).
- **Secrets:** only the production environment holds them (D-38, D-39). Secret
  scanning and gitleaks watch the repository.

## Not in this review

The rest of step 4.7 needs a person or the maintainer's own hands:

- an accessibility test with a screen reader, by a person
  ([accessibility.md](accessibility.md#not-covered)): not done. It follows the
  web application's redesign, planned after release 0.5.0
  ([D-42](decisions.md#d-42-the-screen-reader-test-after-the-redesign));
- a run with a real wallet extension: done on 2026-11-17 and 18 with MetaMask,
  one request from funding to settlement. It found three faults, all fixed: an
  account that MetaMask had not allowed on the network (#93), transactions that
  a smart account's relayer sends (#94), and simulated orbits treated as too
  old (#95);
- the verifier key and the backup key leaving the maintainer's machine, apart from
  one encrypted offline copy each ([P4-11](decisions.md#p4-11-keys)): done on
  2026-11-17. The copies are in the maintainer's password manager.
