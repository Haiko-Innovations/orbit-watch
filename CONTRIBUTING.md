# Contributing to Orbit Watch

**English** · [Suomi](CONTRIBUTING.fi.md)

Thank you for your interest! Orbit Watch is an open protocol and reference
implementation for requesting, delivering, independently verifying and
settling satellite observations. It is a community project: amateur
observers, astronomers and developers are all welcome.

By participating you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Where to start

- Issues labelled [`good first issue`](https://github.com/Haiko-Innovations/orbit-watch/labels/good%20first%20issue)
  are small and self-contained. Typical examples:
  - **a new verification check** (for example a check on observation cadence),
  - **a new observation format** or a missing part of IOD or CCSDS TDM,
  - **a new simulated station profile** (for example a visual observer with binoculars).
- Questions and ideas are welcome as issues too. Use the issue templates.
- If you observe satellites yourself, trying the station quality meter on your
  own data and telling us what was confusing is a valuable contribution.

## Ground rules

These follow from the [project plan](README.md) and are not up for debate in a single PR:

1. **Civilian objects only.** Requests may only target objects on the allow-list,
   built from the public GP catalogue. Do not add support for military,
   intelligence or classified objects.
2. **Simulated data is always labelled.** Every simulated dataset sets
   `"simulated": true` (JSON), carries the simulation marker (IOD) or the
   simulation comment (TDM). Never remove these markers.
3. **Verification is deterministic.** The same input must produce a
   byte-identical report on every machine and every supported Python version.
   No wall-clock time, randomness without a fixed seed, or unordered iteration
   in reports. If you change the verification logic, bump the method version.
4. **The core has no blockchain and no money.** Settlement is a replaceable
   adapter that comes in later phases.
5. **Check sources, do not guess.** When you use a library, a data source or a
   standard, link to the current official documentation in the PR. Do not write
   versions, URLs or addresses from memory.
6. **Respect data providers.** Code that downloads orbit data must follow the
   provider's usage policy (for CelesTrak: download once per update, stop on any
   non-200 response).

## Development setup

The Python core lives in [`core/`](core). You need Python 3.12 or newer.

With [uv](https://docs.astral.sh/uv/) (what CI uses):

```sh
cd core
uv sync --locked
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

With plain pip:

```sh
cd core
python -m venv .venv
. .venv/bin/activate
pip install -e . pytest ruff
pytest
```

## Pull requests

- Work on a branch and open a pull request against `main`. PRs are squash-merged.
- CI (the `tarkistus` check) must pass: lint, tests on the oldest and newest
  supported Python, a plain `pip install`, secret scanning and a vulnerability audit.
- Add or update tests. Every bug fix should come with a test that fails without it.
- Keep PRs focused. A new check, a new format or a new station profile is a good size.
- Do not commit secrets, API keys or personal data. Real observations from other
  people need their permission and attribution before they go into the repository.

## Language

English is the primary language for code, comments, documentation, commit
messages, issues and pull requests. Some key documents also have a Finnish
translation (`*.fi.md`). If you change a document that has a translation,
update the translation too, or say in the PR that you could not and a
maintainer will do it. If the versions differ, the English version applies.

## Licence

Orbit Watch is licensed under the [Apache License 2.0](LICENSE). By submitting a
contribution you agree that it is licensed under the same terms (section 5 of
the licence). Observation data published through Orbit Watch defaults to
CC BY 4.0.

## Security

Please do not report security problems in public issues. See [SECURITY.md](SECURITY.md).
