# Deployment

Phase 4, step 4.5 ([P4-02](decisions.md#p4-02-hosting-on-vercel-and-neon),
[P4-03](decisions.md#p4-03-vercels-own-address-first),
[P4-05](decisions.md#p4-05-portable-by-design),
[P4-10](decisions.md#p4-10-the-databases-protection),
[P4-11](decisions.md#p4-11-keys),
[P4-12](decisions.md#p4-12-releases-and-deployment),
[D-38](decisions.md#d-38-the-service-on-vercel-and-neon)).

> **Testnet only, no real value.** The public service runs on Base Sepolia with
> SIMULATED data. It is not announced yet (step 4.8).

The public testnet service runs on Haiko Innovations' Vercel Pro team (`eemil`)
as the project `orbit-watch`, at **https://orbit-watch-tan.vercel.app**, with
a Neon PostgreSQL database from the Vercel Marketplace (`orbit-watch-db`, Free
plan). Both are in Frankfurt. Nothing in the code is specific to Vercel but
[`vercel.json`](../vercel.json) and [`core/asgi.py`](../core/asgi.py): the same
service runs anywhere as `uvicorn orbit_watch.asgi:app`, or as the
[container image](api.md#running-the-image).

## How it is built

`vercel.json` makes one deployment of two
[services](https://vercel.com/docs/services), so the web application and the API
always ship and roll back together:

- **`web`** (`web/`): Vite builds the web application (`npm ci --ignore-scripts`,
  `npm run build`), and Vercel's network serves it at `/`, with the same
  security headers as the API (`core/tests/test_deployment.py` keeps them
  equal) and a year's cache for the hashed files in `/assets/`.
- **`api`** (`core/`): a Python function in Frankfurt (`fra1`) for `/v1/…`.
  `uv sync --locked --no-dev --no-editable --extra api --extra evm` installs the
  package from `core/uv.lock` with its API and chain extras. The function is
  `core/asgi.py`, which is only `orbit_watch.asgi`'s application, set up by
  the environment. The tests and the sources stay out of the bundle (the
  package is installed), about 150 MB.
- **A cron job** calls `GET /v1/internal/follow` every 15 minutes, with
  `CRON_SECRET` as its bearer token: the follower
  ([P4-06](decisions.md#p4-06-the-service-runs-on-its-own)). Cron jobs run on
  production deployments only.

## Settings

Only the production environment has settings. A preview has none: its API
answers every call `503 not_configured`, and its web application says that the
service does not answer ([P4-12](decisions.md#p4-12-releases-and-deployment)).

| Variable | Type | Value |
|---|---|---|
| `DATABASE_URL` (and Neon's other `PG*`, `POSTGRES_*` variables) | Config, set by the Neon integration | the Neon database, through its pooler, as the database's owner |
| `ORBIT_WATCH_DATABASE_ROLE` | Config | `orbit_watch_app`: every transaction runs as this role, which may only read and write the service's tables |
| `ORBIT_WATCH_DATABASE_SSLMODE` | Config | `verify-full`, checked against the root certificates of `certifi` |
| `ORBIT_WATCH_NETWORK` | Config | `base-sepolia`: the escrow, the Safe and the public RPC endpoint from the deployment record |
| `ORBIT_WATCH_ORIGINS` | Config | `https://orbit-watch-tan.vercel.app,https://orbit-watch-eemil.vercel.app`: where wallets sign in from |
| `ORBIT_WATCH_CLIENT_IP_HEADER` | Config | `x-real-ip`, for the [limits](api.md#limits-against-abuse) |
| `CRON_SECRET` | Secret | random, 64 hex characters: the follower's token |
| `ORBIT_WATCH_VERIFIER_KEY` | Secret | the escrow's verifier key, `0x…` ([D-24](decisions.md#d-24-the-base-sepolia-deployment)) |
| `ORBIT_WATCH_BACKUP_TOKEN` | Secret | random, 64 hex characters: the backup workflow's token, also in the GitHub environment `backup` ([operations.md](operations.md#backups)) |
| `ORBIT_WATCH_BACKUP_RECIPIENT` | Config | the age public key that backups are encrypted to |
| `ORBIT_WATCH_READ_ONLY` | Config | set to `1` only during an incident ([read-only mode](operations.md#read-only-mode)) |
| `ORBIT_WATCH_CHAIN_RPC` | Secret | a dedicated RPC endpoint, once one is chosen; until then Base's public endpoint ([D-38](decisions.md#d-38-the-service-on-vercel-and-neon)) |

The limits and the station coordinates' precision take `serve`'s defaults.
Secrets are written from a pipe, so that they appear in no command line,
history or output, and never pulled to a developer's machine
(`vercel env pull` is not used for production):

```sh
openssl rand -hex 32 | tr -d '\n' | vercel env add CRON_SECRET --environment production --sensitive --yes
```

## The database

Neon was added from the Marketplace for the production environment only, in
Frankfurt, on the Free plan, without Neon Auth:

```sh
vercel integration add neon --name orbit-watch-db --meta region=fra1 --meta auth=false \
  --billing-plan free_v3 --environment production --no-env-pull
```

The database's owner, from `DATABASE_URL`, runs the migrations when a new
deployment first opens the database. It then makes sure that the role
`orbit_watch_app` exists, without a login, may read and write the schema's
tables and sequences and nothing else, and that the owner may switch to it.
Every transaction then begins with `SET LOCAL ROLE orbit_watch_app`, which holds
behind Neon's pooler too. So a mistake in the service can delete rows, but it
cannot drop or alter a table.

The connection comes back by itself when Neon has scaled to zero, and the
service uses no server-side prepared statements, which a pooler in transaction
mode does not keep.

Neon's Free plan restores up to six hours back. Daily encrypted backups,
monitoring and read-only mode are in [operations.md](operations.md).

## Deploying and rolling back

Vercel's production branch is **`main`**
([D-38](decisions.md#d-38-the-service-on-vercel-and-neon)). Every other branch
and every pull request gets a preview without settings.

- **Deploy:** merge a pull request to `main`. Vercel builds it and makes it
  current. A release tag (`v0.5.0`) names a commit that has been deployed.
- **Roll back** with Vercel's
  [instant rollback](https://vercel.com/docs/instant-rollback): the dashboard's
  Instant Rollback on an earlier production deployment, or

  ```sh
  vercel rollback <deployment-url>
  ```

  It points the production domains at that deployment again, with its build,
  its settings as they were then and its cron jobs, without building anything.
  So a rollback after a secret was changed brings the old secret back.
- **After a rollback,** merges to `main` still build, but Vercel does not make
  them current. Fix forwards, usually by reverting the change in a pull
  request, then make the fixed deployment current again:

  ```sh
  vercel promote <deployment-url>
  ```

- A rollback across a migration does not work, since the older version refuses
  a newer schema (`newer_schema`); fix forwards instead, or restore the
  database (step 4.6).

No deployment credential is in GitHub: Vercel's GitHub app builds the
deployments.

## The firewall

A rule in Vercel's firewall limits every path to 300 requests per 60 seconds per
IP address, in front of the service's own limits
([D-36](decisions.md#d-36-limits-the-body-limit-and-the-dedicated-rpc-endpoint)):

```sh
vercel firewall rules add "Orbit Watch: 300 requests per minute per IP" \
  --condition '{"type":"path","op":"pre","value":"/"}' --action rate_limit \
  --rate-limit-keys ip --rate-limit-requests 300 --rate-limit-window 60 --yes
vercel firewall publish   # asks a person to approve
```

## Logs

The service writes no IP address to its own logs. Vercel keeps runtime logs for
30 days with Observability Plus, which the privacy notice says
([D-38](decisions.md#d-38-the-service-on-vercel-and-neon)). The function logs
its settings when it starts: the database's host and name, the escrow and the
verifier's address, never a password or a key.

```sh
vercel logs --deployment <url>
```

## Checking it

```sh
curl https://orbit-watch-tan.vercel.app/v1/health            # 200, the version
curl https://orbit-watch-tan.vercel.app/v1/chain             # Base Sepolia, the escrow
curl https://orbit-watch-tan.vercel.app/v1/health/follower   # 200 once the cron job runs
```
