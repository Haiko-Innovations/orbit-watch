"""The service's side of the web application (phase 3, step 3.1).

The built app is served on the API's own origin with a strict content security policy
(decision D-25), and requests that invite observers are public (decision D-26). The app
itself is tested in web/ (Vitest and Playwright).
"""

from pathlib import Path

import pytest
from starlette.testclient import TestClient
from test_api import REQUESTER, STATION, funded_request, new_key, world  # noqa: F401

from orbit_watch.api import CONTENT_SECURITY_POLICY, create_app
from orbit_watch.sim.scenarios import REQUEST


@pytest.fixture
def built(tmp_path):
    """A stand-in for web/dist."""
    web = tmp_path / "dist"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<!doctype html><title>Orbit Watch</title>")
    (web / "assets" / "app.js").write_text("console.log('SIMULATED');")
    return web


def test_open_requests_are_public_until_reserved(world):  # noqa: F811
    client = world["client"]
    requester = new_key(world, REQUESTER, "requester")
    listed = lambda: client.call("GET", "/v1/public/open-requests").json()["requests"]  # noqa: E731

    document = dict(REQUEST, request_id="SIM-REQ-0002")
    assert client.call("POST", "/v1/requests", requester, {"request": document}).status_code == 201
    assert listed() == []  # a draft is the requester's own

    world["clock"].at("2026-11-01T12:01:00Z")
    assert client.call("POST", "/v1/requests/SIM-REQ-0002/open", requester).status_code == 200
    [opened] = listed()
    assert opened["request_id"] == "SIM-REQ-0002" and opened["status"] == "open"
    assert opened["request"] == document and opened["simulated"] is True
    assert opened["requester"] == REQUESTER and opened["split"] is None
    assert opened["terms"]["window_start"] == "2026-11-01T15:00:00.000Z"
    assert opened["terms"]["target_norad_id"] == REQUEST["target"]["norad_id"]

    # Funded and reserved: the reserved request is no longer listed, the open one is.
    funded_request(world, "SIM-REQ-0001")
    assert [r["request_id"] for r in listed()] == ["SIM-REQ-0002"]

    # Nothing of the reserved request or of anyone's key appears, and no key is needed.
    text = client.call("GET", "/v1/public/open-requests").text
    assert '"SIM-REQ-0001"' not in text
    assert requester not in text and world["admin"] not in text


def test_a_funded_request_shows_its_rewards(world):  # noqa: F811
    client = world["client"]
    requester = new_key(world, REQUESTER, "requester")
    client.call("POST", "/v1/admin/grants", world["admin"], {"party": REQUESTER, "points": 500})
    document = dict(REQUEST, request_id="SIM-REQ-0003")
    client.call("POST", "/v1/requests", requester, {"request": document})
    client.call("POST", "/v1/requests/SIM-REQ-0003/open", requester)
    client.call(
        "POST",
        "/v1/requests/SIM-REQ-0003/fund",
        requester,
        {"observer": 100, "reviewer": 10, "platform_fee": 0},
    )
    [funded] = client.call("GET", "/v1/public/open-requests").json()["requests"]
    assert funded["status"] == "funded"
    assert funded["split"] == {"observer": 100, "reviewer": 10, "platform_fee": 0}


def test_the_built_app_is_served_on_the_apis_origin(world, built):  # noqa: F811
    client = TestClient(create_app(world["service"], clock=world["clock"], web=built))
    page = client.get("/")
    assert page.status_code == 200 and "<title>Orbit Watch</title>" in page.text
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/v1/health").json()["status"] == "ok"  # the API still answers
    assert client.get("/nothing-here").status_code == 404
    for response in (page, client.get("/v1/health"), client.get("/v1/requests")):
        headers = response.headers
        assert headers["content-security-policy"] == CONTENT_SECURITY_POLICY
        assert headers["x-content-type-options"] == "nosniff"
        assert headers["referrer-policy"] == "no-referrer"
    assert "script-src 'self'" in CONTENT_SECURITY_POLICY
    assert "frame-ancestors 'none'" in CONTENT_SECURITY_POLICY


def test_the_app_needs_a_build(world, tmp_path):  # noqa: F811
    with pytest.raises(ValueError, match=r"index\.html"):
        create_app(world["service"], web=tmp_path / "empty")


def test_serve_with_the_web_application(tmp_path, built, capsys, monkeypatch):
    import uvicorn

    from orbit_watch.cli import EXIT_USAGE, main

    directory = tmp_path / "svc"
    missing = main(["serve", "--dir", str(directory), "--web", str(tmp_path / "nope")])
    assert missing == EXIT_USAGE
    assert "npm run build" in capsys.readouterr().err

    served = {}

    def fake_run(app, host, port):
        served["page"] = TestClient(app).get("/").text

    monkeypatch.setattr(uvicorn, "run", fake_run)
    assert main(["serve", "--dir", str(directory), "--web", str(built)]) == 0
    assert "Orbit Watch" in served["page"]
    assert "Web application on http://127.0.0.1:8000/" in capsys.readouterr().out
    assert Path(built / "index.html").exists()
