"""Vercel's entry to the service (phase 4, step 4.5; decision P4-05): only the package's ASGI
application, set up by environment variables. Any other host runs
``uvicorn orbit_watch.asgi:app``, or the container image. See docs/deployment.md."""

from orbit_watch.asgi import app

__all__ = ["app"]
