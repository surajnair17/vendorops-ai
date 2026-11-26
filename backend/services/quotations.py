"""Limited quotation checks using stated values, not tax law or commercial approval."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal, localcontext

from backend.schemas.business import BusinessDocument, issues_for, source_issues

QUANTA = {"USD": "0.01", "INR": "0.01", "EUR": "0.01", "GBP": "0.01", "JPY": "1"}


def assess_quote(document: BusinessDocument, pages: list[str], as_of: date) -> dict:
    findings = []
    checks = []

    def finding(kind, field, message, expected=None, actual=None, difference=None, evidence=None):
        findings.append(
            {
                "type": kind,
                "field": field,
                "message": message,
                "expected": str(expected) if expected is not None else None,
                "actual": str(actual) if actual is not None else None,
                "difference": str(difference) if difference is not None else None,
                "evidence": evidence or [],
                "review_status": "open",
            }
        )

    def cites(*fields):
        return [document.evidence[f].model_dump() for f in fields if f in document.evidence]

    for issue in dict.fromkeys(issues_for(document) + source_issues(document, pages)):
        finding("validation_issue", "source", issue)
    for field in (
        "document_date",
        "valid_until",
        "payment_terms",
        "taxable_amount",
        "tax_rate_percent",
    ):
        if getattr(document, field) is None:
            finding("missing_field", field, f"Missing {field}; confirm against the original PDF.")
    if document.valid_until is None:
        checks.append({"field": "valid_until", "status": "skipped", "reason": "Expiry is unknown"})
    else:
        expired = as_of > document.valid_until
        checks.append({"field": "valid_until", "status": "failed" if expired else "passed"})
        if expired:
            finding(
                "quote_expired",
                "valid_until",
                "The quotation expired before the assessment date.",
                f">= {as_of}",
                document.valid_until,
                evidence=cites("valid_until"),
            )
        if document.document_date and document.valid_until < document.document_date:
            finding(
                "invalid_date_range",
                "valid_until",
                "Expiry precedes the quotation date.",
                f">= {document.document_date}",
                document.valid_until,
                evidence=cites("document_date", "valid_until"),
            )
    if document.document_date and document.document_date > as_of:
        finding(
            "future_document_date",
            "document_date",
            "The quotation is dated after this assessment.",
            f"<= {as_of}",
            document.document_date,
            evidence=cites("document_date"),
        )

    quantum = QUANTA.get(document.currency)
    if quantum is None:
        finding(
            "unsupported_currency",
            "currency",
            "Confirm a supported currency before calculating.",
            actual=document.currency,
            evidence=cites("currency"),
        )
        checks.append(
            {"field": "financials", "status": "skipped", "reason": "Unknown rounding rule"}
        )
    else:
        with localcontext() as context:
            context.prec = 50
            rounding = Decimal(quantum)

            def check(field, inputs, calculate, evidence):
                actual = inputs[-1]
                if any(value is None for value in inputs):
                    checks.append({"field": field, "status": "skipped", "reason": "Missing inputs"})
                    finding(
                        "incomplete_calculation",
                        field,
                        "The calculation needs explicit values; missing amounts are not zero.",
                        actual=actual,
                        evidence=evidence,
                    )
                    return
                expected = calculate().quantize(rounding, rounding=ROUND_HALF_UP)
                # Expected amounts are rounded once; do not round away a reported discrepancy.
                difference = actual - expected
                checks.append(
                    {
                        "field": field,
                        "status": "passed" if difference == 0 else "failed",
                        "expected": str(expected),
                        "actual": str(actual),
                    }
                )
                if difference:
                    finding(
                        "calculation_mismatch",
                        field,
                        "The stated amount differs from the calculation.",
                        expected,
                        actual,
                        difference,
                        evidence,
                    )

            for index, item in enumerate(document.items):
                check(
                    f"items.{index}.total",
                    [item.quantity, item.unit_price, item.discount, item.tax, item.total],
                    lambda item=item: item.quantity * item.unit_price - item.discount + item.tax,
                    [entry.model_dump() for entry in item.evidence],
                )
            check(
                "subtotal",
                [item.total for item in document.items] + [document.subtotal]
                if document.items
                else [None, document.subtotal],
                lambda: sum(item.total for item in document.items),
                [entry.model_dump() for item in document.items for entry in item.evidence]
                + cites("subtotal"),
            )
            check(
                "tax",
                [document.taxable_amount, document.tax_rate_percent, document.tax],
                lambda: document.taxable_amount * document.tax_rate_percent / Decimal(100),
                cites("taxable_amount", "tax_rate_percent", "tax"),
            )
            if document.items and any(item.taxable is not None for item in document.items):
                taxable_inputs = []
                for item in document.items:
                    taxable_inputs.append(item.taxable)
                    if item.taxable:
                        taxable_inputs.extend([item.quantity, item.unit_price, item.discount])
                taxable_inputs.append(document.taxable_amount)
                check(
                    "taxable_amount",
                    taxable_inputs,
                    lambda: (
                        sum(
                            (item.quantity * item.unit_price - item.discount)
                            for item in document.items
                            if item.taxable
                        )
                        if any(item.taxable for item in document.items)
                        else Decimal(0)
                    ),
                    [entry.model_dump() for item in document.items for entry in item.evidence]
                    + cites("taxable_amount"),
                )
            check(
                "total",
                [
                    document.subtotal,
                    document.discount,
                    document.tax,
                    document.freight,
                    document.total,
                ],
                lambda: document.subtotal - document.discount + document.tax + document.freight,
                cites("subtotal", "discount", "tax", "freight", "total"),
            )
    return {
        "as_of": as_of.isoformat(),
        "status": "needs_review" if findings else "checks_passed",
        "findings": findings,
        "checks": checks,
        "assessment_version": 1,
    }
