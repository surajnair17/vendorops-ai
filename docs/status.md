# Verification record

## Phase 0 and Phase 1

- Python 3.13.17 environment created.
- 11 tests passed, including Streamlit initial rendering and PDF/API edge cases.
- `scripts/smoke.py` started both servers and verified a real multipart HTTP extraction.
- Initial lint passed after formatting.
- Browser file selection has not been manually exercised; server smoke and Streamlit's test
  harness are separate evidence and do not substitute for that manual check.
- No paid calls or real email deliveries were made.
- Learner exercises and teach-back remain for the user to complete.

## Environment notes

The system Python alias required execution outside the filesystem sandbox. The virtual environment
uses the installed interpreter. Windows application control blocked SQLAlchemy's optional native
extension; the supported pure-Python build is being used. No application-control policy was changed.

On this machine, if a normal SQLAlchemy install encounters the same error:

```powershell
$env:DISABLE_SQLALCHEMY_CEXT = '1'
.\.venv\Scripts\python.exe -m pip install --force-reinstall --no-binary SQLAlchemy 'SQLAlchemy>=2.0,<3'
```

Future live-model, OCR, AWS deployment, delivery, and accuracy claims require explicit live checks.
