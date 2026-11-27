import re
from decimal import ROUND_HALF_UP, Decimal, localcontext

from pydantic import ValidationError

from backend import db
from backend.errors import AppError
from backend.schemas.business import BusinessDocument


def normalized(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def current_business(connection, identifier: str):
    document = db.get(connection, identifier, "document")
    if not document["data"]["revision_id"]:
        raise AppError(422, "structure_required", "Extract and review structured data first.")
    revision = db.get(connection, document["data"]["revision_id"], "revision")
    if not revision["data"]["structured"]:
        raise AppError(422, "structure_required", "No valid structured record is available.")
    try:
        structured = BusinessDocument.model_validate(revision["data"]["structured"])
    except ValidationError as error:
        raise AppError(
            422,
            "structured_review_required",
            "Stored fields no longer pass validation. Review and save a corrected revision.",
        ) from error
    return document, revision, structured


def supplier_key(connection, name: str | None) -> str:
    key = normalized(name)
    aliases = {
        normalized(r["data"]["alias"]): normalized(r["data"]["canonical"])
        for r in db.all_records(connection, "supplier_alias")
    }
    return aliases.get(key, key)


def match_candidates(connection, identifier: str) -> dict:
    _, invoice_revision, invoice = current_business(connection, identifier)
    if invoice.document_type != "invoice":
        raise AppError(422, "invoice_required", "Select an invoice to find a purchase order.")
    candidates = []
    for document in db.all_records(connection, "document"):
        if not document["data"]["revision_id"]:
            continue
        try:
            _, revision, order = current_business(connection, document["id"])
        except AppError:
            continue
        if order.document_type != "purchase_order":
            continue
        supplier_match = bool(invoice.supplier and order.supplier) and (
            supplier_key(connection, invoice.supplier) == supplier_key(connection, order.supplier)
        )
        exact = bool(
            invoice.po_number
            and order.document_number
            and supplier_match
            and normalized(invoice.po_number) == normalized(order.document_number)
        )
        candidates.append(
            {
                "document_id": document["id"],
                "revision_id": revision["id"],
                "number": order.document_number,
                "supplier": order.supplier,
                "exact_match": exact,
                "supplier_match": supplier_match,
                "review_required": bool(
                    invoice_revision["data"].get("issues") or revision["data"].get("issues")
                ),
            }
        )
    exact = [c for c in candidates if c["exact_match"] and not c["review_required"]]
    return {
        "candidates": candidates,
        "automatic_match": exact[0]["document_id"] if len(exact) == 1 else None,
    }


def compare(
    invoice: BusinessDocument, order: BusinessDocument, mapping: dict[int, int] | None = None
) -> list[dict]:
    # Two 18-digit inputs can have a 36-digit product. Avoid default-context rounding.
    with localcontext() as context:
        context.prec = 50
        return _compare(invoice, order, mapping)


def _compare(
    invoice: BusinessDocument, order: BusinessDocument, mapping: dict[int, int] | None
) -> list[dict]:
    findings = []

    def add(kind, field, expected=None, actual=None, evidence=None):
        if evidence is None:
            parts = field.split(".")
            evidence = {}
            for owner, document in (("invoice", invoice), ("purchase_order", order)):
                if parts[0] in {"invoice", "purchase_order"} and parts[0] != owner:
                    continue
                path = parts[1:] if parts[0] in {"invoice", "purchase_order"} else parts
                if path[0] == "items" and len(path) > 1 and path[1].isdigit():
                    index = int(path[1])
                    if index < len(document.items):
                        evidence[owner] = [e.model_dump() for e in document.items[index].evidence]
                elif path[0] in document.evidence:
                    evidence[owner] = [document.evidence[path[0]].model_dump()]
        difference = (
            actual - expected
            if isinstance(actual, Decimal) and isinstance(expected, Decimal)
            else None
        )
        findings.append(
            {
                "type": kind,
                "field": field,
                "expected": str(expected) if expected is not None else None,
                "actual": str(actual) if actual is not None else None,
                "difference": str(difference) if difference is not None else None,
                "evidence": evidence or [],
                "review_status": "open",
            }
        )

    if invoice.currency != order.currency or not invoice.currency:
        add("currency_mismatch", "currency", order.currency, invoice.currency)
        return findings
    quantum = {"USD": "0.01", "INR": "0.01", "EUR": "0.01", "GBP": "0.01", "JPY": "1"}.get(
        invoice.currency
    )
    if quantum is None:
        add("unsupported_currency", "currency", actual=invoice.currency)
        return findings
    rounding = Decimal(quantum)
    used = set()
    if mapping is not None and (
        len(set(mapping.values())) != len(mapping)
        or any(
            i < 0 or i >= len(invoice.items) or j < 0 or j >= len(order.items)
            for i, j in mapping.items()
        )
    ):
        raise AppError(422, "invalid_line_mapping", "Line mappings must be valid and one-to-one.")
    for index, item in enumerate(invoice.items):
        if mapping is not None and index in mapping:
            choices = [mapping[index]]
        else:
            choices = [
                j
                for j, candidate in enumerate(order.items)
                if item.item_id
                and candidate.item_id
                and normalized(item.item_id) == normalized(candidate.item_id)
            ]
            if not choices:
                choices = [
                    j
                    for j, candidate in enumerate(order.items)
                    if normalized(item.description) == normalized(candidate.description)
                    and normalized(item.unit) == normalized(candidate.unit)
                ]
        if len(choices) != 1 or choices[0] in used:
            add(
                "ambiguous_line" if choices else "unexpected_item",
                f"items.{index}",
                actual=item.description,
                evidence=[e.model_dump() for e in item.evidence],
            )
            continue
        order_index = choices[0]
        used.add(order_index)
        expected = order.items[order_index]
        evidence = {
            "invoice": [e.model_dump() for e in item.evidence],
            "purchase_order": [e.model_dump() for e in expected.evidence],
        }
        if normalized(item.unit) != normalized(expected.unit) or not item.unit:
            add("unit_mismatch", f"items.{index}.unit", expected.unit, item.unit, evidence)
            continue
        for field, kind in (("quantity", "quantity_variance"), ("unit_price", "price_variance")):
            left, right = getattr(expected, field), getattr(item, field)
            if left is None or right is None:
                add("missing_field", f"items.{index}.{field}", left, right, evidence)
            elif left != right:
                add(kind, f"items.{index}.{field}", left, right, evidence)
    for index, item in enumerate(order.items):
        if index not in used:
            add("missing_item", f"purchase_order.items.{index}", item.description)
    for label, document in (("invoice", invoice), ("purchase_order", order)):
        for index, item in enumerate(document.items):
            values = (item.quantity, item.unit_price, item.discount, item.tax, item.total)
            if any(value is None for value in values):
                add("incomplete_calculation", f"{label}.items.{index}")
                continue
            expected = (item.quantity * item.unit_price - item.discount + item.tax).quantize(
                rounding, rounding=ROUND_HALF_UP
            )
            if expected != item.total:
                add("line_total_mismatch", f"{label}.items.{index}.total", expected, item.total)
        if document.subtotal is not None and all(item.total is not None for item in document.items):
            subtotal = sum((item.total for item in document.items), Decimal(0))
            if subtotal != document.subtotal:
                add("subtotal_mismatch", f"{label}.subtotal", subtotal, document.subtotal)
        amounts = (
            document.subtotal,
            document.discount,
            document.tax,
            document.freight,
            document.total,
        )
        if any(amount is None for amount in amounts):
            add("incomplete_calculation", f"{label}.total")
        else:
            expected = (
                document.subtotal - document.discount + document.tax + document.freight
            ).quantize(rounding, rounding=ROUND_HALF_UP)
            if expected != document.total:
                add("total_mismatch", f"{label}.total", expected, document.total)
    return findings


def report_is_stale(connection, report: dict) -> bool:
    return any(
        db.get(connection, report["data"][f"{side}_id"], "document")["data"]["revision_id"]
        != report["data"][f"{side}_revision_id"]
        for side in ("invoice", "po")
    )
