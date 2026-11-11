import json

from orbit_watch.cli import main


def test_convert_roundtrip_through_all_formats(tmp_path, examples_dir, monkeypatch, capsys):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1793577600")
    formats = examples_dir / "formats"
    sites = str(formats / "sites.json")
    tdm_path, iod_path = tmp_path / "x.tdm", tmp_path / "x.iod"
    assert main(["convert", str(formats / "observation-set.json"), "-o", str(tdm_path)]) == 0
    assert main(["convert", str(formats / "observation-set.json"), "-o", str(iod_path)]) == 0
    assert main(["convert", str(tdm_path), "--sites", sites, "-o", str(tmp_path / "t.json")]) == 0
    assert main(["convert", str(iod_path), "--sites", sites, "-o", str(tmp_path / "i.json")]) == 0
    from_tdm = json.loads((tmp_path / "t.json").read_text())
    from_iod = json.loads((tmp_path / "i.json").read_text())
    assert from_tdm["simulated"] is True and from_iod["simulated"] is True
    assert len(from_tdm["observations"]) == 3 and len(from_iod["observations"]) == 3
    assert "SIMULATED" in capsys.readouterr().out


def test_committed_examples_match_converter(tmp_path, examples_dir, monkeypatch):
    """examples/formats/*.iod and *.tdm are generated from the JSON example."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1793577600")
    formats = examples_dir / "formats"
    for suffix in (".iod", ".tdm"):
        out = tmp_path / f"observation-set{suffix}"
        assert main(["convert", str(formats / "observation-set.json"), "-o", str(out)]) == 0
        assert out.read_bytes() == (formats / f"observation-set{suffix}").read_bytes()


def test_missing_sites_is_a_usage_error(tmp_path, examples_dir, capsys):
    iod_path = examples_dir / "formats" / "observation-set.iod"
    assert main(["convert", str(iod_path), "-o", str(tmp_path / "x.json")]) == 2
    assert "--sites" in capsys.readouterr().err


def test_invalid_json_is_explained(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text('{"format": "orbit-watch/observation-set"}')
    assert main(["convert", str(bad), "-o", str(tmp_path / "x.tdm")]) == 2
    assert "required property" in capsys.readouterr().err


def test_license_copy_matches_root(repo_root):
    assert (repo_root / "core" / "LICENSE").read_bytes() == (repo_root / "LICENSE").read_bytes()


def test_version_is_the_same_everywhere(repo_root):
    import tomllib
    from importlib import metadata

    from orbit_watch import __version__

    pyproject = tomllib.loads((repo_root / "core" / "pyproject.toml").read_text())
    assert pyproject["project"]["version"] == __version__
    assert metadata.version("orbit-watch") == __version__


def test_changelog_has_unreleased_and_current_version(repo_root):
    from orbit_watch import __version__

    changelog = (repo_root / "CHANGELOG.md").read_text()
    assert "## [Unreleased]" in changelog
    if ".dev" not in __version__:
        assert f"## [{__version__}] - " in changelog
