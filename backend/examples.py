"""Exact synthetic text/response pairs. These are fixtures, not an extraction model."""

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
