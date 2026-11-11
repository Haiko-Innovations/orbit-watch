import json

from orbit_watch.cli import main


def test_demo_and_validate(tmp_path, capsys):
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert "SIMULATED" in text and "NO" not in text.split("ok", 1)[1]
    common = [
        "--request",
        str(out / "request.json"),
        "--catalog",
        str(out / "catalog.json"),
        "--policy",
        str(out / "target-policy.json"),
    ]
    report_path = tmp_path / "r.json"
    acceptable = out / "datasets" / "acceptable" / "delivery.json"
    assert main(["validate", str(acceptable), *common, "--report", str(report_path)]) == 0
    assert json.loads(report_path.read_text())["verdict"] == "pass"
    assert report_path.read_bytes() == (out / "datasets/acceptable/report.json").read_bytes()
    wrong = out / "datasets" / "wrong_target" / "delivery.json"
    previous = ["--previous", str(out / "datasets/acceptable/observations.json")]
    assert main(["validate", str(wrong), *common, *previous]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert main(["validate", str(wrong), *common, *previous, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["verdict"] == "fail"


def test_simulate_command(tmp_path, capsys):
    target = tmp_path / "sim.iod"
    assert (
        main(
            [
                "simulate",
                "--target",
                "339003",
                "--profile",
                "sim-azel-mount",
                "--start",
                "2026-11-01T00:00:00Z",
                "--end",
                "2026-11-02T00:00:00Z",
                "--seed",
                "4",
                "-o",
                str(target),
            ]
        )
        == 0
    )
    assert target.read_text().startswith("# orbit-watch: simulated=true")
    assert "SIMULATED" in capsys.readouterr().out


def test_simulate_unknown_object(tmp_path):
    assert (
        main(
            [
                "simulate",
                "--target",
                "25544",
                "--start",
                "2026-11-01T00:00:00Z",
                "--end",
                "2026-11-02T00:00:00Z",
                "-o",
                str(tmp_path / "x.json"),
            ]
        )
        == 2
    )


def test_score_station_command(tmp_path, capsys, examples_dir):
    sim = examples_dir / "simulated"
    report = tmp_path / "q.json"
    code = main(
        [
            "score-station",
            str(sim / "quality" / "observations.iod"),
            "--sites",
            str(sim / "quality" / "sites.json"),
            "--catalog",
            str(sim / "catalog.json"),
            "--report",
            str(report),
        ]
    )
    assert code == 0
    assert "0.25 s ahead of UTC" in capsys.readouterr().out
    assert report.read_bytes() == (sim / "quality" / "report.json").read_bytes()
