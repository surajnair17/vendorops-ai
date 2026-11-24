# Guided demonstration and learning checkpoints

Start API, Streamlit, and worker. In a fresh data directory run:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.demo
```

This seeds a synthetic PO and invoice with a $1 unit-price difference (8%), an inactive price-tolerance
policy, an unconfirmed rule, and a draft email. It makes no approvals or deliveries and refuses a
backend with live calls enabled.

1. Open PDF Text and extract a generated digital PDF. Explain the HTTP request and the JSON fields.
2. Open Documents. Inspect source text beside structured JSON, provider mode, citations, and revision
   history. Correct one field and show the retained original revision. Explain why the report is stale.
3. Open Compare. Make a fresh comparison, verify the price difference by hand, and explain unique PO
   matching. Upload another matching PO to demonstrate ambiguity, then choose a PO explicitly.
4. Open Policies. Activate the demo policy, inspect its text, and confirm the tolerance rule as the
   operator. Create a saved policy assessment on Compare. The observed difference remains visible
   even when classified within tolerance. Explain retrieval versus rule execution.
5. On Actions create a new draft referencing that report and assessment. Read its recipient, content,
   findings, and evidence. Submit, approve, edit, and demonstrate that editing clears approval.
   Submit and approve the edited revision, then explicitly execute simulated delivery. Inspect the
   worker result and audit history. Explain why provider acceptance differs from inbox delivery.
6. Upload the same invoice again and inspect duplicate warnings. Test a corrupt PDF and an unknown
   fixture document to show controlled failures. Show a scan returning no text in the stateless endpoint.
7. Explain the separate live OCR/cloud gate. Only after the live checklist is completed should a
   demonstration claim a scanned-document workflow or a real SES inbox delivery works.
8. Show the evaluation report and name one limitation. Demonstrate restore into a new directory and
   policy reindexing. Explain why pending sends are marked unknown after restoring an old backup.

Suggested ten-minute walkthrough: business problem (1 minute), request lifecycle (2), comparison
and policy evidence (3), approval and failure handling (2), evaluation/costs/limitations (2).

Learning exercise: add one metadata field end to end, calculate a comparison manually, and write
one forbidden workflow transition test. Fill in the workbook yourself before considering a learning
phase complete. Code generation and passing fixtures do not demonstrate your understanding.
