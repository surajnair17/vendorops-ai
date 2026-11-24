# Backend

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

The repository stores validated JSON snapshots in SQLite through SQLAlchemy. Documents,
revisions, comparisons, policies, actions, and jobs have separate record kinds. BEGIN IMMEDIATE
serializes state changes. This small single-host design should migrate to relational tables and
PostgreSQL before scaling to several application hosts.

Read [architecture](docs/architecture.md), [operations](docs/operations.md), and
[learning exercises](docs/learning.md).
