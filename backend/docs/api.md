# API examples

[← Documentation](README.md) · [Backend guide](../README.md)

Start the backend at `http://127.0.0.1:8000`. Browse the complete generated contract at
[`/docs`](http://127.0.0.1:8000/docs) or download [`/openapi.json`](http://127.0.0.1:8000/openapi.json).
The local PoC is intended for one operator on a private host.
The request boundary rejects unconfigured hosts (`400`) and browser origins (`403`). JSON bodies
default to 512 KiB; multipart requests allow the file limit plus 64 KiB of framing. Slow uploads
return `408`, oversized requests return `413`, and all error responses carry a stable code/message.
Every PDF route also enforces the configured page and extracted-text budgets before persistence.

## Check availability

```powershell
curl.exe http://127.0.0.1:8000/health
```

```json
{"status": "ok"}
```

Use `curl` in place of `curl.exe` on macOS/Linux.

## Extract a PDF without storing it

```powershell
curl.exe -F "file=@invoice.pdf" http://127.0.0.1:8000/api/v1/documents/extract
```

Example response for a one-page PDF containing `Invoice INV-001`:

```json
{
  "filename": "invoice.pdf",
  "page_count": 1,
  "extracted_text": "Invoice INV-001",
  "character_count": 15,
  "extraction_status": "success",
  "message": "Text extracted successfully."
}
```

`character_count` is the length of the returned text, including page separators. The default
upload limit is **10 MiB = 10,485,760 bytes** and is enforced while reading the actual content.
This route retains no upload and performs no OCR. A readable blank or image-only PDF returns
`200` with `extraction_status: "no_text"` and an explanatory message.

## Store a document for review

```powershell
curl.exe -F "file=@invoice.pdf" http://127.0.0.1:8000/api/v1/documents
```

Use the returned document `id` in subsequent operations:

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/documents/DOCUMENT_ID/structure
curl.exe http://127.0.0.1:8000/api/v1/documents/DOCUMENT_ID
```

The default fixture provider accepts exact generated examples. Create those with
`python -m backend.scripts.generate_samples`; arbitrary source text requires review rather than
receiving fabricated fixture output.

## Workflow map

All paths below are relative to `/api/v1`. The interactive API docs define full request bodies.

| Purpose | Endpoint examples |
| --- | --- |
| Documents and revisions | `GET /documents`, `GET /documents/{id}`, `PATCH /documents/{id}/structured-data` |
| Quotation assessment | `POST /documents/{id}/quote-assessments`, `GET /quote-assessments/{id}` |
| Scanned-page processing | `POST /documents/{id}/ocr`, `GET /jobs/{id}` |
| Matching and comparison | `GET /documents/{id}/match-candidates`, `POST /comparisons` |
| Policy evidence | `GET /policies`, `POST /comparisons/{id}/policy-assessments` |
| Confirmed rules | `POST /rules`, `POST /rules/{id}/confirm` |
| Draft and review | `POST /actions`, `PATCH /actions/{id}`, `POST /actions/{id}/request-review` |
| Approval and execution | `POST /actions/{id}/review`, `POST /actions/{id}/execute` |
| History and operations | `GET /audit`, `GET /metrics`, `GET /jobs` |

Creating a draft does not authorize a send. Review binds approval to an exact revision, and
execution is a separate request. Edits and stale source reports invalidate approval. Job-creating
background requests return `202`, a job ID, and a status URL; poll that URL to inspect the outcome.

Unknown fixture documents can receive an initial human-reviewed record through the correction
endpoint with `expected_revision_id: null` and `expected_document_version` from the document.
Quotation assessments require the current `expected_revision_id` and an explicit `as_of` date.
They return `201` synchronously and make no model call. See [quotation review](quotations.md)
for example bodies, fields, checks, and stale-report behavior.

## Error contract

```json
{
  "error": {
    "code": "upload_too_large",
    "message": "The PDF exceeds the configured size limit."
  }
}
```

| Status | Meaning |
| --- | --- |
| `400` | Empty upload or unreadable/corrupt PDF |
| `413` | Upload or processing budget exceeded |
| `415` | Unsupported filename extension or actual content |
| `422` | Missing/invalid inputs or password-protected PDF |
| `409` | Stale revision or invalid workflow transition |
| `500` | Unexpected failure with a generic public message |

Handle errors using the stable `error.code` and display `error.message`. On uncertain delivery,
inspect the job and reconcile the result before considering another send.
