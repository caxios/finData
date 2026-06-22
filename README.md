# findata

Commercial financial-data API serving US **SEC EDGAR** and Korean **OpenDART**
data, with caching, authentication, metering, and scheduled ingestion.

- **Library layer** (`findata.sec`, `findata.dart`) — call SEC/DART, return data.
- **Server layer** (`findata.server`) — FastAPI + SQLite (Postgres-ready) with
  API keys, quotas/rate limits, usage metering, and background ingestion.

See [docs/architecture.md](docs/architecture.md) for the full design and
[docs/api_implementation_plans/](docs/api_implementation_plans/) for the
commercial-API build plans.

## Install

```bash
pip install -e ".[server]"          # API server
pip install -e ".[server,dart]"     # + OpenDART ingestion
```

## Run

```bash
# API server (reads SQLite under ~/.findata by default)
python -m findata.server.app
# or: uvicorn findata.server.app:app --port 8000

# Background worker (Form 4 polling + scheduled financials/DART ingestion)
python -m findata.server.worker

# One-time universe warm-up (first deploy)
python -m findata.server.ingestion.warmup
```

## Configuration (environment)

| Variable | Purpose | Default |
|---|---|---|
| `FINDATA_DATA_DIR` | SQLite/data directory | `~/.findata` |
| `DATABASE_URL` | Storage backend (unset → SQLite) | — |
| `OPEN_DART_API`, `GOOGLE_API_KEY`, `TAVILY_API_KEY` | Upstream provider keys | — |
| `FINDATA_SEC_USER_AGENT` | SEC `User-Agent` (name + email) | bundled default |
| `FINDATA_CORS_ORIGINS` | Allowed CORS origins (comma-sep or `*`) | `*` |
| `FINDATA_GATEWAY_SECRET` | Require `X-Gateway-Secret` (owner-exempt) | unset (off) |
| `FINDATA_UPSTREAM_MONTHLY_BUDGET_USD` | Circuit-breaker budget for paid endpoints | unset (off) |
| `ENABLE_FORM4_POLLER` | Run Form 4 poller in this process | `0` |
| `ENABLE_SCHEDULED_INGESTION` | Run scheduled ingestion in this process | `0` |
| `ENABLE_PDF_DOWNLOAD` | Enable `/api/download-pdf` (needs Playwright) | `0` |
| `FINDATA_UNIVERSE_FILE` | Override the data-universe JSON | bundled |

## Tests

```bash
pytest -q
```

## Deployment

See [docs/api_implementation_plans/08_deployment_and_infra.md](docs/api_implementation_plans/08_deployment_and_infra.md)
and [infra/README.md](infra/README.md) for the AWS topology, secrets, gateway,
worker scheduling, backup/DR, and monitoring runbook.
