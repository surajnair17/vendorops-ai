# Evaluate observed behavior

Generate the synthetic corpus before running the two offline checks:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.generate_samples
.\.venv\Scripts\python.exe -m backend.scripts.evaluate
.\.venv\Scripts\python.exe -m backend.scripts.evaluate_retrieval
```

The corpus has 60 digital documents, 20 scanned invoice variants, five policies, labelled queries,
and adversarial PDFs. Documents and their scans share a template split. The last five template-B
examples per type form the held-out group; do not tune a live prompt on those examples.

Fixture extraction maps exact known text to predetermined data. Its scores test wiring and arithmetic.
The fixture embedding hashes words; its retrieval score tests index plumbing. Neither establishes
live accuracy. The five-policy set makes recall@5 especially weak; add distractors and held-out
queries before using the 90% target as a meaningful release claim.

## Measured fields

Header and line-item field accuracy use reference values; decimal representations such as 50 and
50.00 compare numerically. Extra lines are penalized. Missing/invalid outputs remain in the denominator.
Line IDs must be unique to align by ID; when both IDs are absent the scorer uses position.
Citation scoring checks exact page/quote presence and reports missing citations separately.
It does not establish that a quote supports the model's interpretation.

Matching runs the real service against an isolated in-memory database. It reports correct selections,
incorrect selections, and abstentions. Deterministic findings are compared with separately stored
expected findings. Missing invoice/PO outputs count as missed labelled findings. Digital and scanned
records have separate scores. Scan character error rate is Levenshtein edits per reference character
after whitespace normalization. Timing measures the observed pipeline, excluding human review.

## Saved live/OCR outputs

You can score observed outputs without making any service calls. Save JSON with this shape:

```json
{
  "provider": "live_bedrock_textract",
  "split": "test",
  "include_scans": true,
  "documents": {
    "INV-001-scan.pdf": {
      "pages": ["Actual OCR text returned by the provider"],
      "structured": {"document_type": "invoice"},
      "latency_seconds": 8.4
    }
  }
}
```

Use the full structured document from the application in a real run. Include the matching digital PO
outputs when scoring scanned comparisons. The provider label is supplied by the person recording
the run; the scorer preserves it without authenticating its provenance.
Every labelled document in the selected split is scored, including missing observations. This
prevents omitting failed documents from inflating the score. The default split is `test`, including
scans; set `include_scans` to false only for a deliberately digital-only run.

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.evaluate --results backend/artifacts/live-observations.json --output backend/artifacts/live-evaluation.json
```

With an agreed cloud budget and configured model, `evaluate --live` invokes Bedrock only for held-out
digital documents. `evaluate_retrieval --live` explicitly opts in to live embeddings. Both require
the application live-call gates. The OCR job workflow must run separately before scan outputs can
be scored. Always store model/prompt/schema versions and keep original outputs with the report.

Release targets remain: 95% critical digital fields, 90% policy recall@5 on an expanded set, no incorrect
automatic matches, valid evidence, and passing deterministic/workflow tests. A missed target requires
improvement or a narrower supported scope. Cloud costs are reported separately using the cost worksheet.
