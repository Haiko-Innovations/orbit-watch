"""The service's container image (phase 4, step 4.2): what it is built from.

The image itself is built and tested end to end in CI (web/playwright.config.ts with
``ORBIT_WATCH_E2E_IMAGE``); these checks keep its inputs pinned.
"""

import re


def test_the_image_is_built_from_images_pinned_by_digest(repo_root):
    dockerfile = (repo_root / "Dockerfile").read_text(encoding="utf-8")
    images = re.findall(r"^FROM (\S+)", dockerfile, re.MULTILINE)
    images += re.findall(r"^COPY --from=(\S+:\S+)", dockerfile, re.MULTILINE)
    assert len(images) == 4
    for image in images:
        assert re.fullmatch(r"[a-z0-9./-]+:[0-9][0-9a-z.-]*@sha256:[0-9a-f]{64}", image), image


def test_the_image_uses_the_ci_versions(repo_root):
    """The same uv as CI, the web application's Node line and the oldest supported Python
    (the one CI runs the end-to-end tests with)."""
    dockerfile = (repo_root / "Dockerfile").read_text(encoding="utf-8")
    workflow = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    uv = re.search(r"ghcr\.io/astral-sh/uv:([0-9.]+)@", dockerfile).group(1)
    assert f'version: "{uv}"' in workflow
    node = re.search(r"^FROM node:(\d+)\.", dockerfile, re.MULTILINE).group(1)
    assert (repo_root / "web" / ".nvmrc").read_text(encoding="utf-8").strip() == node
    pythons = set(re.findall(r"^FROM python:(\d+\.\d+)\.", dockerfile, re.MULTILINE))
    assert pythons == {"3.12"}
    assert "--python 3.12 pytest" in workflow


def test_only_the_sources_reach_the_image(repo_root):
    """The build context is an allowlist: local state, keys and build output stay out."""
    lines = [
        line
        for line in (repo_root / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    ]
    assert lines[0] == "*"
    allowed = {line[1:] for line in lines if line.startswith("!")}
    assert allowed == {
        "core/pyproject.toml",
        "core/uv.lock",
        "core/README.md",
        "core/LICENSE",
        "core/src/",
        "web/",
    }
    assert {"web/node_modules/", "web/.e2e-stack/", "web/demo/"} <= set(lines)
