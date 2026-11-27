# Backend

[← Project overview](../README.md) · [Documentation](docs/README.md) · [API examples](docs/api.md)

Owns the API, PDF processing, persistence, matching, policies, approvals, worker, cloud adapters,
tests, evaluation scripts, deployment assets, and learning documentation.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
.\.venv\Scripts\python.exe -m backend.worker
.\.venv\Scripts\python.exe -m pytest backend/tests -q
```

Settings come from backend/.env; environment variables take precedence. Runtime data defaults
to backend/data. requirements-cloud.txt adds boto3; requirements-dev.txt adds testing tools.
No AWS client is created during import.
Production dependency versions and hashes are in `requirements-lock.txt`; Docker and CI install
that checked set. SQLite handles the policy index. See [hardening and migration](docs/hardening.md).
Local OCR uses a separately installed Tesseract executable (`VENDOROPS_TESSERACT_COMMAND`); the
backend container includes it. Deployment and local-login instructions are in [AWS setup](docs/aws-setup.md).

## Module map

| Path | Responsibility |
| --- | --- |
| `main.py` | FastAPI composition, error handling, and request metrics |
| `middleware.py` | Host/origin validation, bounded request bodies, and private response headers |
| `config.py` | Typed settings and live-service defaults |
| `db.py`, `migrations/` | Transactions, snapshots, and schema versions |
| `routes/` | Endpoints grouped by business capability |
| `schemas/` | Pydantic document contracts and validation |
| `services/` | PDF processing, structured extraction, quotation checks, comparison, policies, OCR, workflows |
| `worker.py` | Durable background job execution |
| `scripts/` | Synthetic samples, demo seeding, evaluation, backup, and smoke checks |
| `tests/` | API, domain, concurrency, job, and recovery checks |
| `infra/` | Compose, deployment templates, and bootstrap assets |
| `docs/` | Explanations, learning exercises, runbooks, and measured evidence |

## Persistence boundary

The repository stores validated JSON snapshots in SQLite through SQLAlchemy. Documents,
revisions, comparisons, policies, actions, and jobs have separate record kinds. BEGIN IMMEDIATE
serializes state changes. This small single-host design should migrate to relational tables and
PostgreSQL before scaling to several application hosts.

Read [architecture](docs/architecture.md), [operations](docs/operations.md), and
[learning exercises](docs/learning.md).
