# The Orbit Watch service as a container image (phase 4, step 4.2; decisions P4-05 and
# P4-06): the API, the built web application and the follower, with no state of its own.
# Everything it keeps is in the PostgreSQL database named by ORBIT_WATCH_DATABASE_URL (or
# DATABASE_URL); any number of containers may share one. Testnet only, no real value.
#
#   docker build --tag orbit-watch .
#   docker run --read-only --tmpfs /tmp --env ORBIT_WATCH_DATABASE_URL=... \
#     --publish 127.0.0.1:8000:8000 orbit-watch [serve options, e.g. --network base-sepolia]
#
# Base images are pinned by digest to releases at least 14 days old (2026-11-16):
# Node 26.12.1 (the web application's .nvmrc line), Python 3.12.15 (the oldest supported
# Python, as in CI) and uv 0.11.16 (as in CI). Dependabot proposes updates.

# --------------------------------------------------------------------- the web application
FROM node:26.12.1-slim@sha256:94816674c62774da0d099a947bf4613b9e1972a2733abd0d0cd80e795f8411d0 AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json web/.npmrc ./
# Exactly the lock file; no package runs an install script (decision P3-02).
RUN npm ci --ignore-scripts
# The web application imports the contracts' ABIs from the Python package.
COPY core/src/orbit_watch/chain/abi /src/core/src/orbit_watch/chain/abi
COPY web/ ./
RUN npm run build

# --------------------------------------------------------------------- the Python service
FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS service
COPY --from=ghcr.io/astral-sh/uv:0.11.16@sha256:440fd6477af86a2f1b38080c539f1672cd22acb1b1a47e321dba5158ab08864d /uv /uvx /bin/
# Bytecode compiled at build time (the file system is read-only at run time); the image's
# own Python, never a downloaded one.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
# The locked, hash-checked dependencies first (a layer of their own), then the package,
# installed non-editable so that the final image needs no source tree.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=core/uv.lock,target=uv.lock \
    --mount=type=bind,source=core/pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev --no-editable --extra api --extra evm
COPY core/pyproject.toml core/uv.lock core/README.md core/LICENSE ./
COPY core/src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --extra api --extra evm

# --------------------------------------------------------------------- the image
FROM python:3.12.15-slim@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704
LABEL org.opencontainers.image.title="Orbit Watch" \
      org.opencontainers.image.description="Orbit Watch service: API, web application and follower. Testnet only, no real value." \
      org.opencontainers.image.source="https://github.com/Haiko-Innovations/orbit-watch" \
      org.opencontainers.image.licenses="Apache-2.0"
RUN groupadd --system --gid 10001 orbit-watch \
    && useradd --system --uid 10001 --gid 10001 --no-create-home --home-dir /nonexistent \
       --shell /usr/sbin/nologin orbit-watch
COPY --from=service /app/.venv /app/.venv
COPY --from=web /src/web/dist /app/web
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
USER orbit-watch
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/v1/health' % os.environ['PORT'], timeout=4)"]
# Listens on $PORT (8000; a platform may set another). Arguments given to `docker run` are
# added to `orbit-watch serve`, and a later option wins (e.g. --host 127.0.0.1).
ENTRYPOINT ["/bin/sh", "-c", "exec orbit-watch serve --host 0.0.0.0 --port \"$PORT\" --web /app/web \"$@\"", "orbit-watch"]
