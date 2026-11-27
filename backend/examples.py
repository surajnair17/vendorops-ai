"""Exact synthetic text/response pairs. These are fixtures, not an extraction model."""

from copy import deepcopy
from decimal import Decimal


def examples() -> list[dict]:
    result = []
    for index in range(20):
        for kind, prefix in (("purchase_order", "PO"), ("invoice", "INV"), ("quotation", "Q")):
            price = Decimal("12.50") + (Decimal("1.00") if kind == "invoice" and index % 2 else 0)
            quantity = Decimal(4)
            total = quantity * price
            number = f"{prefix}-{index + 1:03}"
            text = (
                f"VendorOps synthetic {kind}\nSupplier: Example Supplies\n"
                f"Number: {number}\nPO: PO-{index + 1:03}\nCurrency: USD\n"
                f"Item: SKU-001 | Paper boxes | {quantity} box | {price} | {total}\n"
                f"Subtotal: {total}\nDiscount: 0\nTax: 0\nFreight: 0\nTotal: {total}"
            )
            if index >= 15:
                text = "HELD-OUT TEMPLATE B\n" + text.replace("Supplier:", "Vendor:")
            data = {
                "document_type": kind,
                "supplier": "Example Supplies",
                "document_number": number,
                "po_number": f"PO-{index + 1:03}",
                "currency": "USD",
                "items": [
                    {
                        "item_id": "SKU-001",
                        "description": "Paper boxes",
                        "quantity": "4",
                        "unit": "box",
                        "unit_price": str(price),
                        "discount": "0",
                        "tax": "0",
                        "total": str(total),
                        "evidence": [{"page": 1, "quote": "Paper boxes"}],
                    }
                ],
                "subtotal": str(total),
                "discount": "0",
                "tax": "0",
                "freight": "0",
                "total": str(total),
                "evidence": {
                    "document_number": {"page": 1, "quote": number},
                    "supplier": {"page": 1, "quote": "Example Supplies"},
                    "po_number": {"page": 1, "quote": f"PO-{index + 1:03}"},
                    "currency": {"page": 1, "quote": "USD"},
                    "total": {"page": 1, "quote": f"Total: {total}"},
                    "subtotal": {"page": 1, "quote": f"Subtotal: {total}"},
                    "discount": {"page": 1, "quote": "Discount: 0"},
                    "tax": {"page": 1, "quote": "Tax: 0"},
                    "freight": {"page": 1, "quote": "Freight: 0"},
                },
            }
            result.append({"text": text, "data": data, "split": "test" if index >= 15 else "dev"})
    return result


def quotation_examples() -> list[dict]:
    """A separate commercial-terms demo; the original evaluation corpus stays unchanged."""
    text = (
        "VendorOps synthetic quotation\nSupplier: Sample Engineering\nNumber: Q-TERMS-001\n"
        "Date: 2026-11-01\nValid until: 2026-12-31\nCurrency: USD\n"
        "Payment terms: Payment due 30 days after delivery.\n"
        "Parts | quantity 2 each | unit price 125.00 | discount 0 | line tax 0 | "
        "total 250.00 | taxable yes\n"
        "Setup | quantity 1 job | unit price 50.00 | discount 0 | line tax 0 | "
        "total 50.00 | taxable no\n"
        "Subtotal: 300.00\nDiscount: 0\nTaxable amount: 250.00\nTax rate: 6.25%\n"
        "Tax: 15.63\nFreight: 0\nTotal: 315.63"
    )
    data = {
        "document_type": "quotation",
        "supplier": "Sample Engineering",
        "document_number": "Q-TERMS-001",
        "document_date": "2026-11-01",
        "valid_until": "2026-12-31",
        "currency": "USD",
        "payment_terms": "Payment due 30 days after delivery.",
        "subtotal": "300.00",
        "discount": "0",
        "taxable_amount": "250.00",
        "tax_rate_percent": "6.25",
        "tax": "15.63",
        "freight": "0",
        "total": "315.63",
        "items": [],
        "evidence": {},
    }
    for name, quantity, unit, price, total, taxable in (
        ("Parts", "2", "each", "125.00", "250.00", True),
        ("Setup", "1", "job", "50.00", "50.00", False),
    ):
        data["items"].append(
            {
                "description": name,
                "quantity": quantity,
                "unit": unit,
                "unit_price": price,
                "discount": "0",
                "tax": "0",
                "total": total,
                "taxable": taxable,
                "evidence": [
                    {
                        "page": 1,
                        "quote": next(
                            line for line in text.splitlines() if line.startswith(name + " |")
                        ),
                    }
                ],
            }
        )
    for field, label in (
        ("supplier", "Supplier"),
        ("document_number", "Number"),
        ("document_date", "Date"),
        ("valid_until", "Valid until"),
        ("currency", "Currency"),
        ("payment_terms", "Payment terms"),
        ("subtotal", "Subtotal"),
        ("discount", "Discount"),
        ("taxable_amount", "Taxable amount"),
        ("tax_rate_percent", "Tax rate"),
        ("tax", "Tax"),
        ("freight", "Freight"),
        ("total", "Total"),
    ):
        data["evidence"][field] = {
            "page": 1,
            "quote": next(line for line in text.splitlines() if line.startswith(label + ":")),
        }
    return [{"text": text, "data": data, "split": "dev"}]


def recording_examples() -> list[dict]:
    """Two explicitly labelled arithmetic examples for the recorded walkthrough."""
    result = []
    for source in examples()[3:5]:
        data = deepcopy(source["data"])
        data["document_number"] = (
            "PO-DEMO-001" if data["document_type"] == "purchase_order" else "INV-DEMO-001"
        )
        data["po_number"] = "PO-DEMO-001"
        data["document_date"] = "2026-11-27"
        item = data["items"][0]
        text = (
            f"VendorOps synthetic {data['document_type']}\nSupplier: {data['supplier']}\n"
            f"Number: {data['document_number']}\nDate: {data['document_date']}\n"
            f"PO: {data['po_number']}\nCurrency: {data['currency']}\n"
            "Item: SKU-001 | Paper boxes\nQuantity: 4 box\n"
            f"Unit price: {item['unit_price']}\nLine discount: 0\nLine tax: 0\n"
            f"Line total: {item['total']}\nSubtotal: {data['subtotal']}\n"
            f"Discount: 0\nTax: 0\nFreight: 0\nTotal: {data['total']}"
        )
        data["evidence"]["document_number"]["quote"] = data["document_number"]
        data["evidence"]["po_number"]["quote"] = data["po_number"]
        data["evidence"]["document_date"] = {"page": 1, "quote": "Date: 2026-11-27"}
        item["evidence"] = [{"page": 1, "quote": "Item: SKU-001 | Paper boxes"}]
        result.append({"text": text, "data": data, "split": "dev"})
    return result
