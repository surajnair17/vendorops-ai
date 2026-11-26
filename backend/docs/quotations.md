# Quotation review

[Documentation](README.md) · [API examples](api.md) · [Learning workbook](learning.md)

The quotation milestone adds explicit commercial fields and a deterministic assessment. It works
with generated fixtures or manually reviewed records without AWS credentials. Live AI extraction
remains disabled and unmeasured. Quotation ranking and broader commercial advice remain extensions.

## Try it locally

1. Start the API and Streamlit using the root quick start. Generate samples with
   `python -m backend.scripts.generate_samples`.
2. In **Documents**, store `backend/artifacts/samples/quotations/Q-TERMS-001.pdf` and choose
   **Extract structured data**. The exact synthetic sample has a labelled fixture response.
3. Open **Quotes**, select the quotation, and set **Assess as of** to `2026-11-26`.
4. Select **Assess quotation**. Supported checks pass for the sample. This is not purchase approval.
5. Change the assessment date to `2027-01-01`. The quotation is expired, and the report needs review.
6. Correct a field in Documents and save it. The earlier assessment becomes **STALE**. Run another
   assessment to check the new revision.

The sample is separate from the original 60-document extraction benchmark. Passing it does not
establish accuracy on supplier documents. No cloud calls, approvals, or emails occur in these steps.

## Review an unfamiliar scanned quote

Store the PDF in **Documents**, request local OCR, and refresh its job status after the worker
finishes. The **PDF Text** screen also offers an opt-in local OCR action for image-only uploads;
it saves a copy that appears in Documents.

Fixture mode deliberately refuses unknown text. Use **Editable structured JSON** to enter a human
reviewed record, then choose **Save initial reviewed record**. Leave unavailable values `null`.
You can also replace an invalid model output with a reviewed record. Every save retains a revision
with provider `human`. Automatic extraction, human entry, and fixture results remain distinguishable.

Check the original image when OCR numbers look wrong. A readable OCR sentence does not establish
that its table columns or digits are correct. Do not calculate a missing quantity from a price and
total and then present it as extracted evidence. A dash, empty cell, or missing tax row is not zero.
The template defaults to `quotation`; change `document_type` for other business documents.

## Fields and evidence

| JSON field | Representation | Review rule |
| --- | --- | --- |
| `document_date` | ISO date or `null` | Flag dates after the assessment date |
| `valid_until` | ISO date or `null` | Valid through this date; flag expiry or contradictory dates |
| `payment_terms` | Exact text or `null` | Retain for human interpretation; do not execute instructions |
| `tax_rate_percent` | Decimal string from 0 to 100 or `null` | `"6.25"` represents 6.25%, not 0.0625 |
| `taxable_amount` | Nonnegative decimal string or `null` | Compare with explicitly taxable line bases when known |
| `items[].taxable` | `true`, `false`, or `null` | Preserve an unknown taxable status |

Existing fields remain compatible; missing new fields default to `null`. Monetary values and
quantities serialize as decimal strings. Populated headers and amounts need a page citation:

```json
{
  "tax_rate_percent": "6.25",
  "evidence": {
    "tax_rate_percent": {"page": 1, "quote": "Tax rate: 6.25%"}
  }
}
```

Citations must be exact substrings of the stored page text. Tax-rate citations without an explicit
percent marker require review: OCR `6.2508` must not silently become `6.25%`. Placeholder identities
such as `Company Name` or `[123456]` are flagged. Citation presence is not proof that a value was
correctly interpreted. A visual correction whose evidence is absent from OCR remains visibly
unsupported by stored text; the application does not fabricate a supporting quote.

## Supported calculations

Calculations use `Decimal`, a precision of 50, and half-up rounding of expected amounts. USD, EUR,
GBP, and INR round to 0.01; JPY rounds to 1. Other currencies require review. The observed amount
is not rounded to hide a discrepancy.

- Line total: `quantity × unit_price − line discount + line tax`.
- Subtotal: sum of stated line totals.
- Tax: `taxable_amount × tax_rate_percent / 100`.
- Taxable base: sum of `quantity × unit_price − line discount` for explicitly taxable lines,
  only when every line's taxable status and the needed inputs are known.
- Total: `subtotal − document discount + document tax + freight`.

All operands must be explicitly represented. A missing operand produces a skipped check and a
review finding. Line tax and document tax represent separate additions; enter zero only if the
source explicitly states no tax at that level. Multiple tax rates, tax-inclusive prices, percentage
discounts, other charges, or different supplier conventions need manual review and an extended
schema before these formulas apply. This is arithmetic checking, not jurisdiction-specific tax law.
If no line taxability is supplied, the taxable base is not independently reconstructed.

Reports store the document ID, exact revision, assessment date, provider provenance, checks, and
findings. Each mismatch records expected and actual values, their difference, and available source
quotes. Date and validation findings also remain visible. `checks_passed` means the supported
checks passed; it cannot approve a quote, resolve payment terms, or establish a fair market price.

## API lifecycle

Create an initial reviewed record using the version returned by `GET /documents/{id}`:

```json
{
  "expected_revision_id": null,
  "expected_document_version": 1,
  "structured": {"document_type": "quotation"}
}
```

Send this to `PATCH /api/v1/documents/{id}/structured-data`. An incomplete record is saved with
review issues. Missing version returns `422`; a changed document or revision returns `409`.
For corrections, use the current revision ID. Existing correction requests remain compatible.

```text
POST /api/v1/documents/{id}/quote-assessments
{"expected_revision_id": "REVISION_ID", "as_of": "2026-11-26"}

GET /api/v1/documents/{id}/quote-assessments
GET /api/v1/quote-assessments/{assessment_id}
```

Creation returns `201`; a non-quotation returns `422`; a stale revision returns `409`. Assessment
is synchronous and makes no model call. Reading a saved report computes whether its source revision
is now stale. Earlier snapshots are retained, including when OCR replaces text and clears structuring.

## Learning record and next work

Architecture: PDF/OCR text → fixture or reviewed record → Pydantic schema → immutable revision →
Python assessment → saved report → Quotes screen. The frontend communicates through HTTP.

Decision: store optional fields in the existing JSON snapshots. Older records can be read without
a SQL migration; schema and prompt metadata advance to version 2. Keep the assessment separate
from invoice–PO comparisons and from email approval workflows.

Debugging lesson: OCR can change one digit while preserving fluent text. Financial inconsistencies
provide a reason to review the image; they do not identify which cell is wrong. Tests deliberately
change a quantity and verify that the observed value is retained.

Practice: calculate `250 × 6.25 / 100` by hand, explain why 15.625 becomes 15.63, and then change
one quantity in the sample. Predict every affected check before running the assessment. Explain
why a missing discount causes a skipped calculation, and why `checks_passed` is not approval.

Next: measure live model extraction after a credit allowance is agreed, improve OCR table geometry
and per-word confidence, evaluate varied quotation layouts, and define explicit comparison criteria
before ranking multiple quotations. None of these are established by this local milestone.
