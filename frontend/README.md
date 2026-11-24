# Frontend

Streamlit displays extraction, document review, comparisons, policies, actions, and metrics.
It communicates through HTTP only and never imports backend logic or opens the database.

Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run frontend/app.py --server.address 127.0.0.1
.\.venv\Scripts\python.exe -m pytest frontend/tests -q
```

Copy .env.example to .env in this folder. It configures VENDOROPS_BACKEND_URL and the request
timeout. Dependencies and the Dockerfile are separate from the backend.

app.py selects screens, client.py handles HTTP errors, and workspace.py implements review flows.
Structured fields currently use validated JSON editing, a transparent learning interface that
can later become a customer-friendly form.

