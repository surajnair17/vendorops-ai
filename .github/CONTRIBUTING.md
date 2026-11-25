# Contributing to VendorOps AI

Start with the [quick start](../README.md#quick-start), then follow the
[documentation hub](../backend/docs/README.md). Use synthetic documents when developing or reporting issues.

## Where changes belong

- `backend/routes/`: HTTP contracts and request validation.
- `backend/services/`: business logic, providers, and workflows.
- `backend/schemas/`: validated inputs and outputs.
- `backend/tests/`: meaningful API, arithmetic, workflow, and recovery checks.
- `frontend/views/`: one screen per module, each exposing `render()`.
- `frontend/ui.py` and `frontend/assets/`: shared presentation.
- `frontend/client.py`: HTTP access; the frontend must not open the backend database.
- `backend/docs/`: explanations, learning notes, and operational evidence.

Keep the root focused on shared metadata. Preserve the stateless extraction API and keep cloud
calls and real sending disabled by default. Monetary calculations belong in Python with `Decimal`.

## Before opening a pull request

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m backend.scripts.smoke
```

Use `.venv/bin/python` on macOS/Linux. The smoke harness uses isolated fixture data and simulated
delivery. Add tests when behavior changes warrant them; a cosmetic edit does not require a test
that only mirrors markup. Update relevant guides and preview assets when the interface changes.

Describe the problem, resulting behavior, and validation in the pull request. Record any limitation
you could not verify. CI runs offline tests and container startup; it does not deploy to AWS.

## Keep the repository reproducible

Do not commit credentials, `.env` files, customer documents, databases, local AWS profiles,
generated evaluation output, or backups. Configuration examples must use placeholders.
Document measured results separately from release targets and fixture scores.
