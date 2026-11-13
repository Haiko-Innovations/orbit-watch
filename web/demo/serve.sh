#!/usr/bin/env bash
# The phase 3 demo's service on Base Sepolia (testnet, no real value; web/demo/README.md).
#
# A new service directory gets an administrator key first; then the service runs on the
# deployment with the verifier's keystore and serves the built web application. Every
# party signs with its own wallet in the browser; this service holds the verifier key only.
set -euo pipefail

dir="${ORBIT_WATCH_DEMO_DIR:?set ORBIT_WATCH_DEMO_DIR to the state directory of the demo}"
secrets="${ORBIT_WATCH_SECRETS:?set ORBIT_WATCH_SECRETS to the testnet keystores}"
port="${ORBIT_WATCH_DEMO_PORT:-8795}"

cd "$(dirname "$0")/../../core"
mkdir -p "$dir"
chmod 700 "$dir"
if [ ! -s "$dir/admin.key" ]; then
  (umask 077 && uv run --locked orbit-watch keys create --dir "$dir/service" \
    --role admin --party admin:orbit-watch-demo > "$dir/admin.key")
fi
exec uv run --locked orbit-watch serve --dir "$dir/service" --network base-sepolia \
  --verifier-keystore "$secrets/verifier.json" --verifier-password-file "$secrets/password" \
  --web ../web/dist --host 127.0.0.1 --port "$port" --origin "http://127.0.0.1:$port"
