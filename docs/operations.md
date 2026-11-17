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
Actions artifact, for 14 days. A failed run notifies the maintainer.

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
  | The age private key | the maintainer only: `~/secrets/orbit-watch/backup-age-key.txt` on the maintainer's machine, offline in step 4.7 |
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
orbit-watch backup restore restore/*/orbit-watch-*.tar.gz.age \
  --identity ~/secrets/orbit-watch/backup-age-key.txt \
  --database postgresql://postgres@127.0.0.1:5432/drill
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
`GET /v1/health/follower` and the web application. A failed run notifies the
maintainer: GitHub notifies the person who created a scheduled workflow, or who
last changed its schedule, when a run fails, as long as their notification
settings for Actions are on.

- **Checking that an alert arrives:** `gh workflow run uptime.yml -f fail=true`
  fails on purpose, and notifies whoever ran it.
- **When it is late:** GitHub may start a scheduled run late, at busy times. In a
  public repository it turns scheduled workflows off after 60 days without
  activity; turning them back on makes the person who does it the one notified.
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
