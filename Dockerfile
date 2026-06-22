# findata — single image for both the API and the background worker.
# The role is selected by the container command (see CMD / docs):
#   API    : uvicorn findata.server.app:app --host 0.0.0.0 --port 8000   (default)
#   Worker : python -m findata.server.worker
#
# Playwright/Chromium is intentionally NOT installed — /api/download-pdf is
# gated off by default (ENABLE_PDF_DOWNLOAD). To enable it, add a Playwright
# base image / `playwright install --with-deps chromium` and set the env flag.

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    FINDATA_DATA_DIR=/data

WORKDIR /app

# Project metadata + source (only what the package needs; see .dockerignore).
COPY pyproject.toml README.md ./
COPY findata ./findata

# Install the package with the server + DART extras (no editable, no ML/requirements.txt).
RUN pip install ".[server,dart]"

# Persistent data dir (mount a volume / EFS in production).
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Default role: API. Override the command for the worker role.
CMD ["uvicorn", "findata.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
