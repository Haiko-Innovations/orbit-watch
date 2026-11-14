#!/usr/bin/env bash
# The phase 3 demo's service on Base Sepolia (testnet, no real value; web/demo/README.md).
#
# The service keeps its state in PostgreSQL (decision P4-04): the database named by
# ORBIT_WATCH_DATABASE_URL, or else a LOCAL PostgreSQL that this script starts in Docker
# (the image of core/tests/postgres.py, 127.0.0.1 only, trust authentication) and removes
# when the demo ends. A new database gets an administrator key first; then the service runs
# on the deployment with the verifier's keystore and serves the built web application.
# Every party signs with its own wallet in the browser; this service holds the verifier key
# only.
set -euo pipefail

dir="${ORBIT_WATCH_DEMO_DIR:?set ORBIT_WATCH_DEMO_DIR to the state directory of the demo}"
secrets="${ORBIT_WATCH_SECRETS:?set ORBIT_WATCH_SECRETS to the testnet keystores}"
port="${ORBIT_WATCH_DEMO_PORT:-8795}"
image="postgres:18.6@sha256:e3d24f6906d0760bf4da0dae872415391ededefad23fd471c47dc53b0ddf3c42"

cd "$(dirname "$0")/../../core"
mkdir -p "$dir"
chmod 700 "$dir"

container=""
child=""
cleanup() {
  if [ -n "$container" ]; then docker rm --force "$container" > /dev/null 2>&1 || true; fi
}
trap cleanup EXIT
trap 'if [ -n "$child" ]; then kill -TERM "$child" 2> /dev/null || true; wait "$child" || true; fi; exit 0' TERM INT

if [ -z "${ORBIT_WATCH_DATABASE_URL:-}" ]; then
  container="orbit-watch-demo-db-$$"
  docker run --rm --detach --name "$container" --publish 127.0.0.1::5432 \
    --env POSTGRES_HOST_AUTH_METHOD=trust --tmpfs /var/lib/postgresql "$image" > /dev/null
  db_port="$(docker port "$container" 5432/tcp | head -n 1 | sed 's/.*://')"
  for _ in $(seq 1 60); do
    docker exec "$container" pg_isready -h 127.0.0.1 -U postgres -q && break
    sleep 1
  done
  export ORBIT_WATCH_DATABASE_URL="postgresql://postgres@127.0.0.1:${db_port}/postgres"
fi

# A fresh database needs a fresh administrator key.
if [ -n "$container" ] || [ ! -s "$dir/admin.key" ]; then
  (umask 077 && uv run --locked orbit-watch keys create \
    --role admin --party admin:orbit-watch-demo > "$dir/admin.key")
fi
uv run --locked orbit-watch serve --network base-sepolia \
  --verifier-keystore "$secrets/verifier.json" --verifier-password-file "$secrets/password" \
  --web ../web/dist --host 127.0.0.1 --port "$port" --origin "http://127.0.0.1:$port" &
child=$!
wait "$child"
