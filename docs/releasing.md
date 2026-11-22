# Versions and releases

## Version numbers

The Python package follows [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html).
While the version is 0.x, anything may change between minor versions:

- **minor** (0.1.0 → 0.2.0): a finished phase or a larger set of features;
- **patch** (0.1.0 → 0.1.1): fixes and small additions that change no format
  or method;
- development versions between releases end in `.devN` (for example
  `0.2.0.dev0`), so that a report produced from unreleased code is never
  confused with a release.

The version is in two places that a test keeps in sync:
`core/pyproject.toml` and `core/src/orbit_watch/__init__.py`.

## What has a version

Besides the package, these have their own versions, because documents and
reports outlive the software that made them:

| Thing | Where | Current |
|---|---|---|
| Observation set format | `format_version` in the document, schema file name | 1.0, and 1.1 with `source.origin` |
| Request format | `format_version` in the document, schema file name | 1.0, and 1.1 with a replay's `replay` block |
| Delivery, target policy, station profile, sites formats | same | 1.0 |
| Reference-orbit manifest format | `format_version` in the document (`orbit_cache.py`) | 1.0 |
| Verification method | `METHOD_VERSION` in `verify/engine.py`, in every report | 2.1.0 |
| Verification report format | `report_format_version` | 1.1 |
| Station quality meter method and report | `METHOD_VERSION`, `report_format_version` in `quality.py` | 1.1.0, 1.0 |
| Measurement on real data, and its known answers | `RESULTS_FORMAT_VERSION` in `validation.py`, `format_version` in `known-answers.json` | 1.0, 1.0 |

Rules:

- A format gets a new **minor** version (1.1) when optional fields are added,
  and a new **major** version (2.0) when fields are removed or redefined.
  Readers keep accepting older versions as long as reasonably possible.
- The verification method gets a new **patch** version for wording changes, a
  **minor** version for new checks or report fields, and a **major** version
  when pass/fail logic or parameters change.
- Every such change is listed in the changelog.

## The changelog

[CHANGELOG.md](../CHANGELOG.md) follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/). Every pull
request with user-visible changes adds a line under `## [Unreleased]`, in one
of the groups Added, Changed, Deprecated, Removed, Fixed or Security. Internal
refactoring and CI-only changes need no entry.

## Making a release

1. **Release pull request** from `main`:
   - move the `Unreleased` entries under `## [X.Y.Z] - YYYY-MM-DD` and leave an
     empty `Unreleased` section;
   - update the comparison links at the bottom of the changelog;
   - set the version in `core/pyproject.toml` and
     `core/src/orbit_watch/__init__.py`, then run `uv lock` in `core/`;
   - regenerate the demo output: `cd core && uv run orbit-watch demo --out ../examples/simulated`
     (reports contain the version, and CI compares them byte for byte);
   - with the real element sets in the cache, regenerate the real example's quality
     reports (the commands in [examples/real/README.md](../examples/real/README.md))
     and the measurement on real data: `cd core && uv run orbit-watch measure-method`
     ([real-data-validation.md](real-data-validation.md)). Both name the version;
   - update the status in [roadmap.md](roadmap.md).
2. A maintainer merges it after the `tarkistus` check passes.
3. **Tag and GitHub release** on the merge commit:

   ```sh
   git switch main && git pull --ff-only
   git tag -a vX.Y.Z -m "Orbit Watch X.Y.Z"
   git push origin vX.Y.Z
   gh release create vX.Y.Z --title "Orbit Watch X.Y.Z" --notes-file <changelog section>
   ```

4. **Development version:** the next pull request sets the version to the next
   `.dev0` (for example `0.2.0.dev0`) and regenerates the demo output, the real
   example's quality reports and the measurement on real data.

The package is not published on PyPI yet, because "Orbit Watch" is a working
name. Users install from GitHub, a tag pins a release:

```sh
pip install "orbit-watch @ git+https://github.com/Haiko-Innovations/orbit-watch.git@v0.1.0#subdirectory=core"
```
