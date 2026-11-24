# Learning workbook

Use a weekly rhythm: explain, predict, build, practise, verify, teach back.
Suggested allocation: one hour of concepts, three to four building, one to two testing,
and one reviewing. Keep one debugging note and one architecture decision per milestone.

## Phase 0: foundations

- Explain the difference between PowerShell, Python, a virtual environment, and pip.
- Predict which interpreter runs with and without environment activation.
- Practise a small function returning a character count and test it with an empty string.
- Check: a new terminal can run `.venv/Scripts/python.exe -m pytest`.

## Phase 1: extraction

Architecture: browser → Streamlit → HTTP → FastAPI → PyMuPDF → JSON → Streamlit.

Decision: the extraction service receives bytes, not a FastAPI request. This keeps parsing
independent from transport and makes it directly testable.

Exercise: add a `word_count` field to the response and show it in the frontend. Start by defining
what counts as a word. Predict which layers need changing, then add one meaningful test.

Teach back: explain POST, multipart upload, JSON, status codes, Pydantic, and why a scanned PDF
can contain visible writing but no extractable text.

Debugging prompt: if `/health` works but the frontend says it cannot connect, where would you
check the backend address and timeout? What evidence would distinguish a server error from a
connection error?

## Phase 2: structured records

Trace one field from source text through the provider, schema, database, and correction screen.
Explain why a mock passing tests does not establish model accuracy. Add a field end to end.

## Phase 3: comparisons

Compare a small invoice by hand using decimal values. Explain why missing values are not zero,
why a duplicate suspicion is not proof of fraud, and why an ambiguous match needs a human.

## Phase 4: policies

Draw the boundary between retrieving a paragraph and applying an approved rule. Change a chunk
boundary and inspect retrieval. Translate a tolerance paragraph into an explicit numeric rule.

## Phase 5: approvals

Draw the action state machine. Test a forbidden transition. Explain why editing an approved
email invalidates approval, and why a timeout after sending must not trigger an automatic resend.

## Phase 6: cloud

Start with [the AWS learning guide](aws-setup.md). Explain the difference between a Free-plan credit
allowance and a cash budget. Predict which resources a plan with `enable_textract=false` creates,
then compare with the CloudFormation conditions. Change the demo hours in an ignored deployment
record and show how the estimate and review digest change without contacting AWS.

Decision: local OCR keeps scanned PDFs available on the selected Free plan. Regional Nova Lite
avoids the cross-region inference restriction. Explain why Tesseract OCR output is still uncertain
and why SDK stubs do not establish actual account permissions or model accuracy.

Trace an OCR job through storage, Textract, SNS, SQS, and the worker. Explain each IAM permission.
Restart the worker during a job. Compare recorded usage with an actual bill and explain fixed
hosting costs versus per-document costs. Restore a backup before claiming recovery works.

## Phase 7: evaluation

Keep template families and their scans in the same evaluation split. Explain precision, recall,
abstention, and data leakage. Give a ten-minute demonstration with one failure and one limitation.

## Milestone record template

- Date and phase:
- Feature demonstrated:
- Architecture sketch:
- Decision and reason:
- Bug, evidence, and fix:
- Commands run and observed results:
- What remains unverified:
- My exercise and teach-back:

Do not fill in the final line on behalf of the learner. Implementation alone does not demonstrate
understanding.
