"""Running the service on a host such as Vercel (phase 4, step 4.5; decisions P4-05, P4-10,
P4-12 and D-38): the ASGI application set up by environment variables, the database role
that every transaction runs as, a connection that comes back after the server closed it,
and libpq's TLS mode. Everything is LOCAL and SIMULATED.
"""

import argparse
import json
import logging

import pytest
from starlette.testclient import TestClient

from orbit_watch import asgi
from orbit_watch.cli import ServeError, _with_sslmode, build_parser, serve_app
from orbit_watch.storage import Database, Storage, StorageError

ROLE = "orbit_watch_test_app"


@pytest.fixture
def no_settings(monkeypatch):
    for name in (
        "ORBIT_WATCH_DATABASE_URL",
        "DATABASE_URL",
        "ORBIT_WATCH_DATABASE_ROLE",
        "ORBIT_WATCH_DATABASE_SSLMODE",
        "ORBIT_WATCH_NETWORK",
        "ORBIT_WATCH_ORIGINS",
        "ORBIT_WATCH_VERIFIER_KEY",
        "ORBIT_WATCH_CHAIN_RPC",
        "ORBIT_WATCH_LIMITS",
        "ORBIT_WATCH_CLIENT_IP_HEADER",
        "ORBIT_WATCH_STATION_DECIMALS",
        "ORBIT_WATCH_FOLLOW_SECRET",
        "CRON_SECRET",
    ):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


# ---------------------------------------------------------------- the ASGI application


def test_without_a_database_every_call_is_not_configured(no_settings):
    """A preview deployment has no secrets and no database (P4-12)."""
    http = TestClient(asgi.from_environment())
    for method, path in (("GET", "/v1/health"), ("POST", "/v1/requests"), ("GET", "/")):
        reply = http.request(method, path)
        assert reply.status_code == 503
        assert reply.json()["error"]["code"] == "not_configured"
        assert reply.headers["cache-control"] == "no-store"
        assert "default-src" in reply.headers["content-security-policy"]
    assert asgi.app is not None  # importing the module set it up the same way


def test_the_environment_sets_the_service_up(no_settings, database):
    no_settings.setenv("DATABASE_URL", database)
    no_settings.setenv("ORBIT_WATCH_ORIGINS", "https://orbit.example, https://other.example")
    no_settings.setenv("ORBIT_WATCH_CLIENT_IP_HEADER", "x-real-ip")
    no_settings.setenv("ORBIT_WATCH_FOLLOW_SECRET", "a-follow-secret-for-tests")
    app = asgi.from_environment()
    api = app.state.api
    assert api.origins == ("https://orbit.example", "https://other.example")
    assert api.limits is not None and api.client_ip_header == "x-real-ip"
    assert api.station_decimals == 2  # serve's defaults
    assert api.follow_secret == "a-follow-secret-for-tests"
    http = TestClient(app)
    health = http.get("/v1/health")
    assert health.status_code == 200 and health.json()["status"] == "ok"
    assert http.get("/").status_code == 404  # the host serves the web application
    follow = http.get("/v1/internal/follow", headers={"Authorization": "Bearer nope"})
    assert follow.status_code == 401
    assert http.get(
        "/v1/internal/follow", headers={"Authorization": "Bearer a-follow-secret-for-tests"}
    ).json()["followed_at"]
    api.service.storage.close()


def test_a_service_that_cannot_start_says_why_in_its_log_only(no_settings, database, caplog):
    no_settings.setenv("DATABASE_URL", database)
    no_settings.setenv("ORBIT_WATCH_LIMITS", "{not json")
    with caplog.at_level(logging.ERROR, logger="orbit_watch.asgi"):
        reply = TestClient(asgi.from_environment()).get("/v1/health")
    assert reply.status_code == 503
    assert reply.json()["error"]["message"] == "the service cannot start; its log says why"
    assert "--limits" in caplog.text

    caplog.clear()
    no_settings.setenv("ORBIT_WATCH_LIMITS", "off")
    no_settings.setenv("DATABASE_URL", "postgresql://user:hunter2@127.0.0.1:1/none")
    with caplog.at_level(logging.ERROR, logger="orbit_watch.asgi"):
        reply = TestClient(asgi.from_environment()).get("/v1/health")
    assert reply.status_code == 503
    assert "cannot open the database" in caplog.text and "hunter2" not in caplog.text


def test_a_network_needs_the_verifier_key(no_settings, database, caplog):
    no_settings.setenv("DATABASE_URL", database)
    no_settings.setenv("ORBIT_WATCH_NETWORK", "base-sepolia")
    with caplog.at_level(logging.ERROR, logger="orbit_watch.asgi"):
        reply = TestClient(asgi.from_environment()).get("/v1/health")
    assert reply.status_code == 503
    assert "ORBIT_WATCH_VERIFIER_KEY" in caplog.text


def test_the_environment_gives_serve_its_arguments():
    environ = {"ORBIT_WATCH_NETWORK": " base-sepolia ", "ORBIT_WATCH_ORIGINS": "https://a.example,"}
    assert asgi.serve_arguments(environ) == [
        "serve",
        "--network",
        "base-sepolia",
        "--origin",
        "https://a.example",
    ]
    assert asgi.serve_arguments({}) == ["serve"]


def test_the_verifier_key_from_the_environment(no_settings, database):
    """On a chain the verifier key may come from $ORBIT_WATCH_VERIFIER_KEY instead of a
    keystore file; a bad one is refused without being repeated."""
    from anvil import require_local_chain
    from chain_world import VERIFIER, ChainWorld

    require_local_chain()
    world = ChainWorld(database)
    try:
        key = "0x" + bytes(world.account(VERIFIER).key).hex()
        world.service.storage.close()
        args = build_parser().parse_args(
            [
                "serve",
                "--database",
                database,
                "--chain-rpc",
                world.local.w3.provider.endpoint_uri,
                "--escrow",
                world.chain.escrow.address,
                "--from-block",
                "0",
            ]
        )
        app, service, lines = serve_app(args, environ={"ORBIT_WATCH_VERIFIER_KEY": key})
        assert service.chain.verifier.address == world.account(VERIFIER).address
        assert any("All bundled data is SIMULATED" in line for line in lines)
        assert key not in "\n".join(lines)
        assert TestClient(app).get("/v1/chain").status_code == 200
        service.storage.close()

        bad = argparse.Namespace(**vars(args))
        with pytest.raises(ServeError) as refused:
            serve_app(bad, environ={"ORBIT_WATCH_VERIFIER_KEY": "0xnot-a-key-0123"})
        assert "is not a private key" in str(refused.value)
        assert "not-a-key" not in str(refused.value)
    finally:
        world.stop()


# ---------------------------------------------------------------- the database role


def test_every_transaction_runs_as_the_role(database):
    storage = Storage(database, role=ROLE)
    db = storage.db
    assert db.role == ROLE
    with db.transaction():
        assert db.query("SELECT current_user AS u")[0]["u"] == ROLE
        db.execute("INSERT INTO files (sha256, size, content) VALUES (?, 1, ?)", ("a" * 64, b"x"))
        assert db.query("SELECT size FROM files")[0]["size"] == 1
        db.execute("DELETE FROM files")
    # It may read and write the tables, and nothing else.
    for statement in (
        "CREATE TABLE intruder (x INTEGER)",
        "DROP TABLE files",
        "ALTER TABLE files ADD COLUMN y INTEGER",
        "TRUNCATE files",
    ):
        with pytest.raises(Exception, match=r"permission denied|must be owner"), db.transaction():
            db.execute(statement)
    storage.close()
    # Opened again, the user that runs the migrations keeps the grants up to date.
    again = Storage(database, role=ROLE)
    with again.db.transaction():
        assert again.db.query("SELECT count(*) AS n FROM requests")[0]["n"] == 0
    again.close()


def test_the_service_works_as_the_role(database):
    from helpers import catalog_bytes, packaged, policy_bytes

    from orbit_watch.api import create_app, keys
    from orbit_watch.reviewers import ReviewerRegistry
    from orbit_watch.service import VerificationContext, open_service
    from orbit_watch.sim.scenarios import REQUEST
    from orbit_watch.timeutil import parse_utc

    registry = ReviewerRegistry.parse(packaged("reviewers.json"))
    context = VerificationContext(catalog=catalog_bytes(), policy=policy_bytes())
    service = open_service(database, registry, context, database_role=ROLE)
    now = parse_utc("2026-11-01T12:00:00Z")
    with service.storage.db.transaction():
        admin = keys.create_key(service.storage.db, "admin:maintainer", "admin", now)
    http = TestClient(create_app(service, clock=lambda: now))
    auth = {"Authorization": f"Bearer {admin}"}
    made = http.post(
        "/v1/admin/keys",
        json={"party": "requester:sim-cubesat-team", "role": "requester"},
        headers={**auth, "Idempotency-Key": "k1"},
    )
    assert made.status_code == 201, made.text
    requester = {"Authorization": f"Bearer {made.json()['key']}", "Idempotency-Key": "r1"}
    created = http.post("/v1/requests", json={"request": REQUEST}, headers=requester)
    assert created.status_code == 201, created.text
    with service.storage.db.transaction():
        assert service.storage.db.query("SELECT current_user AS u")[0]["u"] == ROLE
    service.storage.close()


def test_a_role_name_is_checked(database):
    with pytest.raises(StorageError, match="not a role name"):
        Storage(database, role='x"; DROP TABLE files; --')


# ---------------------------------------------------------------- a lost connection


def test_a_lost_connection_is_opened_again(database, postgres_server):
    import psycopg

    db = Database(database)
    pid = db.query("SELECT pg_backend_pid() AS p")[0]["p"]
    with psycopg.connect(postgres_server, autocommit=True) as other:
        other.execute("SELECT pg_terminate_backend(%s)", (pid,))
    assert db.query("SELECT 1 AS one") == [{"one": 1}]  # a read on its own
    assert db.query("SELECT pg_backend_pid() AS p")[0]["p"] != pid

    pid = db.query("SELECT pg_backend_pid() AS p")[0]["p"]
    with psycopg.connect(postgres_server, autocommit=True) as other:
        other.execute("SELECT pg_terminate_backend(%s)", (pid,))
    with db.transaction():  # a transaction begins on a new connection
        assert db.query("SELECT 2 AS two") == [{"two": 2}]

    # Inside a transaction a lost connection is an error: the work is not repeated.
    with pytest.raises(psycopg.OperationalError), db.transaction():
        pid = db.query("SELECT pg_backend_pid() AS p")[0]["p"]
        with psycopg.connect(postgres_server, autocommit=True) as other:
            other.execute("SELECT pg_terminate_backend(%s)", (pid,))
        db.query("SELECT 3")
    assert db.query("SELECT 4 AS four") == [{"four": 4}]
    db.close()


# ---------------------------------------------------------------- TLS


def test_the_tls_mode_is_set_with_root_certificates():
    import certifi
    from psycopg.conninfo import conninfo_to_dict

    url = "postgresql://app:secret@ep-x.eu-central-1.aws.neon.tech/neondb?sslmode=require"
    params = conninfo_to_dict(_with_sslmode(url, "verify-full"))
    assert params["sslmode"] == "verify-full"
    assert params["sslrootcert"] == certifi.where()
    assert params["password"] == "secret" and params["host"].endswith("neon.tech")
    assert _with_sslmode(url, None) == url
    given = conninfo_to_dict(_with_sslmode(url + "&sslrootcert=system", "verify-full"))
    assert given["sslrootcert"] == "system"


def test_the_deployment_files_name_the_entry(repo_root):
    """Vercel runs ``core/asgi.py``, which is only the package's application (P4-05)."""
    vercel = json.loads((repo_root / "vercel.json").read_text(encoding="utf-8"))
    api = vercel["services"]["api"]
    assert api["root"] == "core" and api["entrypoint"] == "asgi:app"
    assert "--extra api --extra evm" in api["installCommand"]
    assert "--locked" in api["installCommand"] and "--no-dev" in api["installCommand"]
    entry = (repo_root / "core" / "asgi.py").read_text(encoding="utf-8")
    assert "from orbit_watch.asgi import app" in entry


def test_the_static_pages_get_the_apis_security_headers(repo_root):
    """Vercel serves the web application itself; its headers are the API's (D-25)."""
    from orbit_watch.api import SECURITY_HEADERS

    vercel = json.loads((repo_root / "vercel.json").read_text(encoding="utf-8"))
    rules = vercel["services"]["web"]["headers"]
    everything = next(rule for rule in rules if rule["source"] == "/(.*)")
    given = {h["key"].lower(): h["value"] for h in everything["headers"]}
    assert given == {name.decode(): value.decode() for name, value in SECURITY_HEADERS}
    assert vercel["regions"] == ["fra1"]
    assert vercel["crons"] == [{"path": "/v1/internal/follow", "schedule": "*/15 * * * *"}]
    assert [r["source"] for r in vercel["rewrites"]] == ["/v1/(.*)", "/(.*)"]


def test_the_operations_workflows_keep_to_the_rules(repo_root):
    """Backups and the uptime check (step 4.6, D-39): least privilege, actions pinned to
    commits, the backup token only in its environment, and only age files kept."""
    import re

    folder = repo_root / ".github" / "workflows"
    for name in ("backup.yml", "uptime.yml"):
        text = (folder / name).read_text(encoding="utf-8")
        assert "permissions:\n  contents: read\n" in text, name
        for used in re.findall(r"uses: (\S+)", text):
            assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", used), used
        assert "https://orbit-watch-tan.vercel.app" in text
        assert "${{ inputs" not in text.split("run: |", 1)[1], "inputs reach scripts as env"
    backup = (folder / "backup.yml").read_text(encoding="utf-8")
    assert "environment: backup" in backup
    assert backup.count("secrets.") == 1 and "${{ secrets.ORBIT_WATCH_BACKUP_TOKEN }}" in backup
    assert "retention-days: 14" in backup and "if-no-files-found: error" in backup
    assert backup.index('"age-encryption.org/v1"') < backup.index("upload-artifact")
    uptime = (folder / "uptime.yml").read_text(encoding="utf-8")
    assert "secrets." not in uptime
    for path in ("/v1/health", "/v1/health/follower"):
        assert f'"${{SERVICE}}{path}"' in uptime
    # Just after the follower's run every 15 minutes, never at the busy start of the hour.
    assert '- cron: "17 * * * *"' in uptime
