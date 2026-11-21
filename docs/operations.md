# Operations

Phase 4, step 4.6 ([P4-13](decisions.md#p4-13-operations),
[D-39](decisions.md#d-39-backups-monitoring-and-read-only-mode)): backups,
monitoring, read-only mode, and what to do when something goes wrong. How the
service is deployed and rolled back is in [deployment.md](deployment.md).

> **Testnet only, no real value.** The public service runs on Base Sepolia with
> SIMULATED data. It is not announced yet (step 4.8).

## Backups

Every day at 02:23 UTC the workflow
[`Backup`](../.github/workflows/backup.yml) calls the service's
`GET /v1/internal/backup` with the backup token. The service takes a consistent
backup in one transaction, encrypts it with [age](https://age-encryption.org/v1)
to the maintainer's public key, and streams it out, so plain data never leaves
Vercel and Neon. The job keeps the file only if it is an age file, as a GitHub
Actions artifact, for 14 days. A failed run alerts the maintainer
([alerts](#monitoring)).

- **What is in it:** every table of the service, except what lives for hours at
  most and should not come back after a restore: sessions, sign-in challenges,
  limit counts and the copies of answers kept for idempotency
  ([personal-data.md](personal-data.md)).
- **The format:** age, then gzip and tar: `manifest.json`, with the schema's
  version and each table's columns, row count and SHA-256, and each table's rows
  in PostgreSQL's `COPY` text format. `age -d -i key.txt backup.tar.gz.age | tar
  -xz` opens one without Orbit Watch.
- **The keys:**

  | What | Where |
  |---|---|
  | The age public key | Vercel, production, `ORBIT_WATCH_BACKUP_RECIPIENT` (Config) |
  | The age private key | the maintainer only, offline in a password manager since 2026-11-17 (step 4.7); no machine keeps it |
  | The backup token | Vercel, production, `ORBIT_WATCH_BACKUP_TOKEN` (Secret), and the GitHub environment `backup`, which only `main` may use |

- **Size:** every backup leaves Neon over the network, and Neon's Free plan moves
  5 GB a month. The job warns when a backup is over 50 MB.
- **Neon's own history:** the Free plan restores the database to any moment of
  the last 6 hours, which is the quickest way back from a mistake noticed at once.
- **A server of our own** takes the same backup with
  `orbit-watch backup create --output FILE` (the database and the public key from
  `--database` and `--recipient`, or the environment).

## Restoring

`orbit-watch backup restore` restores a backup into an **empty** database: no
tables in its schema. It applies the migrations up to the backup's version,
loads the rows, checks every table against the manifest, and then applies the
newer migrations, so a newer version restores an older backup.

```sh
gh run download --repo Haiko-Innovations/orbit-watch --dir restore/ \
  "$(gh run list --repo Haiko-Innovations/orbit-watch --workflow Backup \
     --status success --limit 1 --json databaseId --jq '.[0].databaseId')"
(umask 077; cat > restore/age-key.txt)   # paste the key from the password manager, then Ctrl-D
orbit-watch backup restore restore/*/orbit-watch-*.tar.gz.age \
  --identity restore/age-key.txt \
  --database postgresql://postgres@127.0.0.1:5432/drill
rm restore/age-key.txt
```

### The restore drill

Before the launch and after every schema migration, and the result goes in the
[log below](#drills):

1. Restore the newest backup into a new local database, as above (a throwaway
   PostgreSQL container is enough: `docker run --rm -p 127.0.0.1:5432:5432 -e
   POSTGRES_HOST_AUTH_METHOD=trust postgres:18`).
2. Start the service on it, read-only, on another port:
   `orbit-watch serve --database … --read-only --network base-sepolia
   --verifier-keystore … --port 8100`. On a network `serve` needs the escrow's
   verifier key, and checks it; in read-only mode it sends nothing with it.
3. Compare with production: `GET /v1/public/requests` and
   `GET /v1/public/attestations` give the same answers, and the tables' row
   counts printed by the restore match the backup's.
4. Delete the local database and the downloaded file.

The tests restore a backup taken through the API on every pull request
(`core/tests/test_operations.py`), so the format itself is checked all the time.

### Restoring production

1. Turn on [read-only mode](#read-only-mode).
2. If the damage is less than 6 hours old, use Neon's restore instead: Vercel →
   Storage → `orbit-watch-db` → Open in Neon → Restore. Skip to step 6.
3. Take a backup of the damaged database for later (run `Backup` by hand:
   `gh workflow run backup.yml`).
4. In the Neon Console's SQL editor, as the owner: `DROP SCHEMA public CASCADE;
   CREATE SCHEMA public;`.
5. On the maintainer's own machine, restore into it. The connection string comes
   from Neon's Connect dialog; give it only to that command, never in a file:
   `read -rs ORBIT_WATCH_DATABASE_URL && export ORBIT_WATCH_DATABASE_URL`, then
   `orbit-watch backup restore …`, then close the shell.
6. Turn read-only mode off. The follower applies the chain's events since the
   backup by itself; changes that never reached the chain after the backup was
   taken (new keys, station profiles, requests not yet funded) are lost.
7. Check the service ([deployment.md](deployment.md#checking-it)).

## Monitoring

The workflow [`Uptime`](../.github/workflows/uptime.yml) checks the service from
outside at 17 minutes past every hour: `GET /v1/health`,
`GET /v1/health/follower`, `GET /v1/health/reference-orbits` and the web application.

- **The alert is an issue.** A failed run of `Uptime` or `Backup` opens an issue
  labelled `alert: uptime` or `alert: backup` and assigns it to the maintainer
  named in the repository variable `ALERT_ASSIGNEE`, so it reaches them like
  everything else they follow on GitHub. While it is open, later failures add
  nothing; the next run that passes closes it with a link, which tells the
  maintainer that the service is back. GitHub's own notifications of failed runs
  depend on each person's settings, and did not arrive in the first alert check.
- **Checking that an alert arrives:** `gh workflow run uptime.yml -f fail=true`
  fails on purpose and opens the issue; `gh workflow run uptime.yml` then closes
  it.
- **When it is late:** GitHub may start a scheduled run late, at busy times. In a
  public repository it turns scheduled workflows off after 60 days without
  activity, and then no alert comes either: the monthly look at Neon's usage
  (below) is also the time to see that `Uptime` still runs.
- **Neon's hours:** the Free plan gives 100 compute hours a month per project, and
  stops the database for the rest of the month when they are used up. It sends no
  email first, and its usage API is not on the Free plan. The follower runs every
  15 minutes and the database sleeps after 5 minutes, so it is awake about a
  third of the time: roughly 60 to 75 hours a month. The uptime check runs just
  after the follower, while the database is awake. Once a month, and whenever the
  follower falls behind, look at Vercel → Storage → `orbit-watch-db` → Usage. If
  the hours run short: Neon's Launch plan, or the follower every 30 minutes.
- **Neon's other limits:** 1 GB of storage per project, after which writes are
  refused; 5 GB of network transfer a month, after which the database stops.

## Read-only mode

Read-only mode refuses every change with `503 read_only`, and the follower
waits. Reading, the public pages and signing in still work, every page says that
the service is read-only, and backups still work. Use it while something is being
investigated or restored.

```sh
printf 1 | vercel env add ORBIT_WATCH_READ_ONLY --environment production --no-sensitive --yes
vercel redeploy orbit-watch-tan.vercel.app     # the setting applies to new deployments
# … and back:
vercel env rm ORBIT_WATCH_READ_ONLY --environment production --confirm-name ORBIT_WATCH_READ_ONLY
vercel redeploy orbit-watch-tan.vercel.app
```

The follower health check falls behind after 30 minutes in read-only mode, so the
uptime check reminds the maintainer that it is still on.

## Reference orbits

The service verifies deliveries for real objects against the real element sets it keeps
in its database ([D-47](decisions.md#d-47-reference-orbits-in-the-service)), and picks
the one nearest the observations. `GET /v1/public/reference-orbits` names them: the
object, the epoch, the source and the SHA-256, never the elements.

An administrator can upload sets by hand, for example when CelesTrak cannot be reached.
They are labelled as uploaded, in the reports too:

```sh
orbit-watch fetch-gp --catnr 25544 -o iss.csv            # one object, one request
orbit-watch admin upload-orbits iss.csv --api https://orbit-watch-tan.vercel.app --key "$(cat admin.key)"
```

A SIMULATED catalogue, and a set for one of the SIMULATED objects, are refused.

### Fetching

With `ORBIT_WATCH_FETCH_ORBITS=1` (or `serve --fetch-orbits`), the follower also fetches
the element sets that open requests for real objects need
([D-48](decisions.md#d-48-the-follower-fetches-reference-orbits)):
- from CelesTrak, an object's current sets, once per two-hour update, while its request's
  window has not ended and starts within a day;
- from SatChecker, the set nearest the middle of a window that has ended, such as a
  replay's, once.

It asks for at most three objects per run, two seconds apart, and only for objects on the
allow-list that are not SIMULATED. Its answer lists what it asked for and kept, under
`reference_orbits`.

**At the first answer that is not 200 with the object's sets, or no answer at all, the
follower stops asking that source** and waits for a person, as CelesTrak's usage policy
asks. `GET /v1/health/reference-orbits` then answers `503`, and the hourly uptime check
opens an alert issue. What to do is in the
[runbook](#fetching-reference-orbits-stopped).

## Runbooks

### The uptime check failed

1. Open the failed run: which check failed, and with what answer.
2. **`/v1/health` fails:** the deployment is broken. Look at the logs
   (`vercel logs --deployment <url>`) and roll back
   ([deployment.md](deployment.md#deploying-and-rolling-back)).
3. **Only the follower is behind:** the cron job did not run or failed. Its log
   says why: the chain's RPC endpoint, or the database. A database that does not
   answer may have used up Neon's hours ([monitoring](#monitoring)).
4. **Only the web application fails:** its build or Vercel's network; a rollback
   brings back the last good one.
5. **Only `/v1/health/reference-orbits` fails:** the follower has stopped fetching
   reference orbits ([the next runbook](#fetching-reference-orbits-stopped)).

### Fetching reference orbits stopped

`GET /v1/health/reference-orbits` says which source stopped, when, for which object, with
the answer's HTTP status and its first words. Deliveries for objects that already have a
set are still verified; others come out inconclusive until a set is kept.

1. **Read the answer** as CelesTrak's [usage policy](https://celestrak.org/usage-policy.php)
   reads it:
   - `404`: the object has no public data. The object is listed under
     `objects_without_public_data` and is not asked for again. If it should be followed,
     upload a set by hand.
   - `500` or `503`: the source is overloaded. The follower waits at least 15 minutes
     (`not_before`), even once resumed.
   - `403`: CelesTrak refused the service. Read its message before going on. If it blocks
     the address that Vercel shares with other users (P5-02), upload sets by hand until it
     lifts the block.
   - no status: no answer came. The source may be down, or its firewall may block the
     address.
   - `200`: the answer held no element set of the object. Look at the source's page for
     changes to its format.
2. **Upload sets by hand** if requests need them meanwhile ([above](#reference-orbits)).
3. **Resume** once the cause is understood:

   ```sh
   orbit-watch admin resume-orbits --source celestrak --api https://orbit-watch-tan.vercel.app --key "$(cat admin.key)"
   ```

   `--ask-again NORAD_ID` asks for an object again, such as one that answered 404 and has
   public data now. The next run that passes closes the alert issue.

### A deployment broke something

[deployment.md](deployment.md#deploying-and-rolling-back): Vercel's instant
rollback, a fix by pull request, then `vercel promote`.

### A leaked verifier key

The escrow's verifier cannot be changed
([P4-11](decisions.md#p4-11-keys)). With the key, someone can attest wrong
results, which any party can still challenge during the challenge period.

1. Turn on read-only mode, so the service sends nothing more.
2. Watch the escrow's attestations on BaseScan, and challenge wrong ones.
3. Deploy a new escrow with a new verifier key ([base-sepolia.md](base-sepolia.md)),
   start the service on a new, empty database with it, and say what happened.
   Requests in the old escrow settle or expire there; their deposits come back
   to the requesters ([escrow.md](escrow.md)).

### A leaked database password

1. Turn on read-only mode.
2. Change the owner's password: Vercel → Storage → `orbit-watch-db` → Open in
   Neon → Roles → Reset password.
3. Check the production variables that the integration set (`DATABASE_URL` and
   the `PG*` and `POSTGRES_*` ones). Neon's and Vercel's documentation do not say
   whether the integration updates them after a reset; if not, enter the new
   connection string from Neon's Connect dialog in the dashboard.
4. Turn read-only mode off (a redeploy, which takes the new password).
5. Look at what the leaked password may have changed: compare with the last
   backup, and restore if needed.

### A leaked follower secret or backup token

Make a new one from a pipe, so it appears nowhere, and redeploy:

```sh
openssl rand -hex 32 | tr -d '\n' | vercel env add CRON_SECRET --environment production --sensitive --force --yes
vercel redeploy orbit-watch-tan.vercel.app
```

The backup token is also the GitHub environment's secret: write the same value to
both from one pipe (`tee >(…)`), with
`gh secret set ORBIT_WATCH_BACKUP_TOKEN --env backup`. A leaked token reads only
encrypted backups.

### A lost or leaked backup key

1. Make a new age key pair, keep the private key as before, and put the new
   public key in `ORBIT_WATCH_BACKUP_RECIPIENT`; redeploy.
2. Run `Backup` by hand, so that a backup readable with the new key exists.
3. If the key leaked, delete the older backups, which it can read:
   `gh api repos/Haiko-Innovations/orbit-watch/actions/artifacts` lists them,
   and `gh api -X DELETE …/actions/artifacts/<id>` deletes one.

## Drills

| Date | Backup | Result |
|---|---|---|
| 2026-11-17 | The first run of `Backup`, by hand ([run 44034809713](https://github.com/Haiko-Innovations/orbit-watch/actions/runs/44034809713)): 1,823 bytes, schema version 9 | Passed. Restored into a new local database: 21 tables, 4 rows, the service having no requests yet. The service on it, read-only, answered `/v1/health`, `/v1/public/requests`, `/v1/public/attestations` and `/v1/public/open-requests` exactly as production did, and `/v1/chain` too but for the block followed; a change was refused with `503 read_only`. Found: `serve` followed the chain once at start even in read-only mode, which writes; fixed in the same pull request as this entry. |

### Alert checks

| Date | Check | Result |
|---|---|---|
| 2026-11-17 | `Uptime` with `fail=true` ([run 44034861468](https://github.com/Haiko-Innovations/orbit-watch/actions/runs/44034861468)) failed on purpose; a normal run ([44034865633](https://github.com/Haiko-Innovations/orbit-watch/actions/runs/44034865633)) passed | Failed: no notification arrived. The maintainer's GitHub notifications for Actions were off. |
| 2026-11-17 | The same ([run 44038038733](https://github.com/Haiko-Innovations/orbit-watch/actions/runs/44038038733)), with Actions notifications on for GitHub Mobile, failed workflows only | Failed: still no notification. Alerts became issues assigned to the maintainer instead. |
| 2026-11-17 | `Uptime` with `fail=true` after the change ([run 44039304792](https://github.com/Haiko-Innovations/orbit-watch/actions/runs/44039304792)), which opened [#89](https://github.com/Haiko-Innovations/orbit-watch/issues/89); a passing run before it had closed the earlier [#88](https://github.com/Haiko-Innovations/orbit-watch/issues/88) | Passed: both reached the maintainer by email (the maintainer added email to the notification settings during the check). |
