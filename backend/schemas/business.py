import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Number = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, max_digits=18, decimal_places=6)]
Percentage = Annotated[Decimal, Field(ge=0, le=100, allow_inf_nan=False, decimal_places=6)]
SCHEMA_VERSION = 2


class Evidence(BaseModel):
    page: int = Field(ge=1)
    quote: str = Field(min_length=1)


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str | None = None
    description: str
    quantity: Number | None = None
    unit: str | None = None
    unit_price: Number | None = None
    discount: Number | None = None
    tax: Number | None = None
    taxable: bool | None = None
    total: Number | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class BusinessDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal["invoice", "purchase_order", "quotation"]
    supplier: str | None = None
    document_number: str | None = None
    document_date: date | None = None
    valid_until: date | None = Field(default=None, description="Explicit quotation expiry date")
    payment_terms: str | None = Field(default=None, min_length=1)
    po_number: str | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    items: list[LineItem] = Field(default_factory=list)
    subtotal: Number | None = None
    discount: Number | None = None
    tax: Number | None = None
    tax_rate_percent: Percentage | None = Field(
        default=None, description="Explicit percentage, e.g. 6.25 for 6.25%; never a fraction"
    )
    taxable_amount: Number | None = None
    freight: Number | None = None
    total: Number | None = None
    evidence: dict[str, Evidence] = Field(default_factory=dict)


def issues_for(document: BusinessDocument) -> list[str]:
    issues = [
        f"Missing {name}"
        for name in ("supplier", "document_number", "currency", "total")
        if getattr(document, name) is None or getattr(document, name) == ""
    ]
    if not document.items:
        issues.append("No line items")
    for name in ("supplier", "document_number"):
        value = getattr(document, name)
        if value and (
            value.strip().casefold() in {"company name", "supplier name", "quote number"}
            or re.fullmatch(r"\[.+\]|<.+>", value.strip())
        ):
            issues.append(f"Possible template placeholder in {name}; confirm against the source")
    for index, item in enumerate(document.items):
        for field in ("quantity", "unit", "unit_price", "total"):
            if getattr(item, field) is None:
                issues.append(f"Line {index + 1}: missing {field}")
    return issues


def source_issues(document: BusinessDocument, pages: list[str]) -> list[str]:
    """Check citation presence and exact quotes, without claiming semantic entailment."""
    issues = []
    for name in (
        "supplier",
        "document_number",
        "document_date",
        "valid_until",
        "payment_terms",
        "po_number",
        "currency",
        "subtotal",
        "discount",
        "tax",
        "tax_rate_percent",
        "taxable_amount",
        "freight",
        "total",
    ):
        if getattr(document, name) is not None and name not in document.evidence:
            issues.append(f"Missing source citation for {name}")
    rate_evidence = document.evidence.get("tax_rate_percent")
    if (
        document.tax_rate_percent is not None
        and rate_evidence
        and not re.search(r"%|\bpercent(?:age)?\b", rate_evidence.quote, re.IGNORECASE)
    ):
        issues.append(
            "Tax rate citation has no explicit percent marker; review OCR against the PDF"
        )
    for index, item in enumerate(document.items):
        if not item.evidence:
            issues.append(f"Line {index + 1}: missing source citation")
    evidence = list(document.evidence.values())
    evidence.extend(entry for item in document.items for entry in item.evidence)
    for entry in evidence:
        if (
            not entry.quote.strip()
            or entry.page > len(pages)
            or entry.quote not in pages[entry.page - 1]
        ):
            issues.append("Unsupported source citation")
    return list(dict.fromkeys(issues))
