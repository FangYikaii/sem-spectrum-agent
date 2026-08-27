"""Command-line entrypoint for the HTTP service."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("SEM_EDS_CORE_HOST", "0.0.0.0")
    port = int(os.getenv("SEM_EDS_CORE_PORT", "8080"))
    uvicorn.run("sem_eds_core.server:app", host=host, port=port, reload=False)


if __name__ == "__main__":  # pragma: no cover
    main()
