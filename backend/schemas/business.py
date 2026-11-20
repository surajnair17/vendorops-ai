from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Number = Annotated[Decimal, Field(ge=0, allow_inf_nan=False, max_digits=18, decimal_places=6)]


class Evidence(BaseModel):
    page: int = Field(ge=1)
    quote: str


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    item_id: str | None = None
    description: str
    quantity: Number | None = None
    unit: str | None = None
    unit_price: Number | None = None
    discount: Number | None = None
    tax: Number | None = None
    total: Number | None = None
    evidence: list[Evidence] = []


class BusinessDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_type: Literal["invoice", "purchase_order", "quotation"]
    supplier: str | None = None
    document_number: str | None = None
    document_date: date | None = None
    po_number: str | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    items: list[LineItem] = []
    subtotal: Number | None = None
    discount: Number | None = None
    tax: Number | None = None
    freight: Number | None = None
    total: Number | None = None
    evidence: dict[str, Evidence] = {}


def issues_for(document: BusinessDocument) -> list[str]:
    issues = [
        f"Missing {name}"
        for name in ("supplier", "document_number", "currency", "total")
        if getattr(document, name) is None
    ]
    if not document.items:
        issues.append("No line items")
    for index, item in enumerate(document.items):
        for field in ("quantity", "unit", "unit_price", "total"):
            if getattr(item, field) is None:
                issues.append(f"Line {index + 1}: missing {field}")
    return issues
