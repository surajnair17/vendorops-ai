"""Scoring code accepts observed outputs; reference labels never enter a live prompt."""

import re
from decimal import Decimal, InvalidOperation
from statistics import median

from sqlalchemy import create_engine

from backend import db
from backend.schemas.business import BusinessDocument, source_issues
from backend.services.comparison import compare, match_candidates

HEADER_FIELDS = ("document_type", "supplier", "document_number", "po_number", "currency", "total")
LINE_FIELDS = ("item_id", "description", "quantity", "unit", "unit_price", "total")
NUMERIC_FIELDS = {"quantity", "unit_price", "total"}


def equivalent(field: str, expected, actual) -> bool:
    if expected is None or actual is None:
        return expected is actual
    if field in NUMERIC_FIELDS:
        try:
            return Decimal(str(expected)) == Decimal(str(actual))
        except InvalidOperation:
            return False
    return expected == actual


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def character_error_rate(expected: str, actual: str) -> float | None:
    """Levenshtein edits / reference characters after whitespace normalization."""
    expected, actual = [re.sub(r"\s+", " ", value).strip() for value in (expected, actual)]
    if not expected:
        return None
    previous = list(range(len(actual) + 1))
    for i, left in enumerate(expected, start=1):
        current = [i]
        for j, right in enumerate(actual, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1] / len(expected)


def score_group(labels: list[dict], observations: dict[str, dict]) -> dict:
    header_correct = header_missing = line_correct = line_count = valid = 0
    citation_count = unsupported_citations = missing_citations = 0
    durations, ocr_errors, failures, parsed = [], [], [], {}
    for label in labels:
        observation = observations.get(label["file"], {})
        actual = observation.get("structured")
        try:
            document = BusinessDocument.model_validate(actual)
            parsed[label["file"]] = document
            actual = document.model_dump(mode="json")
            valid += 1
        except (ValueError, TypeError):
            actual = {}
            failures.append(
                {
                    "file": label["file"],
                    "reason": observation.get("error_code", "invalid_or_missing_output"),
                }
            )
        for field in HEADER_FIELDS:
            header_correct += field in actual and equivalent(
                field, label["data"].get(field), actual.get(field)
            )
            header_missing += actual.get(field) is None
        expected_items = label["data"].get("items", [])
        items = actual.get("items", [])
        # Use a unique item ID, or position when both IDs are missing. Penalize extra lines.
        for index, expected in enumerate(expected_items):
            matching = [
                item
                for item in items
                if expected.get("item_id") and item.get("item_id") == expected["item_id"]
            ]
            candidate = matching[0] if len(matching) == 1 else {}
            if (
                not expected.get("item_id")
                and index < len(items)
                and not items[index].get("item_id")
            ):
                candidate = items[index]
            line_correct += sum(
                field in candidate and equivalent(field, expected.get(field), candidate.get(field))
                for field in LINE_FIELDS
            )
        line_count += max(len(expected_items), len(items)) * len(LINE_FIELDS)
        if label["file"] in parsed:
            document = parsed[label["file"]]
            citations = list(document.evidence.values()) + [
                e for item in document.items for e in item.evidence
            ]
            citation_count += len(citations)
            pages = observation.get("pages", [])
            unsupported_citations += sum(
                e.page > len(pages) or not e.quote.strip() or e.quote not in pages[e.page - 1]
                for e in citations
            )
            missing_citations += sum(
                "missing" in issue.casefold() for issue in source_issues(document, pages)
            )
        if isinstance(observation.get("latency_seconds"), (int, float)):
            durations.append(observation["latency_seconds"])
        if label["scanned"] and "pages" in observation:
            error = character_error_rate(label["text"], "\n".join(observation["pages"]))
            if error is not None:
                ocr_errors.append(error)
    ordered = sorted(durations)
    return {
        "documents": len(labels),
        "valid_structured_records": valid,
        "completion_rate": ratio(valid, len(labels)),
        "critical_field_accuracy": ratio(header_correct, len(labels) * len(HEADER_FIELDS)),
        "missing_field_rate": ratio(header_missing, len(labels) * len(HEADER_FIELDS)),
        "line_item_field_accuracy": ratio(line_correct, line_count),
        "citations": citation_count,
        "unsupported_citations": unsupported_citations,
        "missing_citations": missing_citations,
        "citation_quote_accuracy": ratio(citation_count - unsupported_citations, citation_count),
        "ocr_character_error_rate": ratio(sum(ocr_errors), len(ocr_errors)),
        "latency_seconds": {
            "median": median(durations) if durations else None,
            "p95": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] if ordered else None,
        },
        "failures": failures,
    }


def score_comparisons(labels: list[dict], observations: dict[str, dict]) -> dict:
    """Exercise the actual matching service in an isolated in-memory database."""
    engine = create_engine("sqlite://")
    correct_matches = incorrect_matches = unresolved = tp = fp = fn = pairs = 0
    valid = {}
    for label in labels:
        try:
            valid[label["file"]] = BusinessDocument.model_validate(
                observations.get(label["file"], {}).get("structured")
            )
        except (ValueError, TypeError):
            continue
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE records (id TEXT PRIMARY KEY, kind TEXT, version INTEGER, "
                "data TEXT, created_at TEXT, updated_at TEXT)"
            )
            for filename, document in valid.items():
                revision = db.create(
                    connection, "revision", {"structured": document.model_dump(mode="json")}
                )
                db.create(connection, "document", {"revision_id": revision["id"]}, filename)
            for label in labels:
                if label["data"]["document_type"] != "invoice":
                    continue
                expected_file = label.get("expected_po_file")
                if not expected_file:
                    continue
                matched = None
                if label["file"] in valid:
                    try:
                        matched = match_candidates(connection, label["file"])["automatic_match"]
                    except Exception:
                        matched = None
                if matched is None:
                    unresolved += 1
                elif matched == expected_file:
                    correct_matches += 1
                else:
                    incorrect_matches += 1
                expected = set(label.get("expected_findings", []))
                predicted = set()
                if label["file"] in valid and expected_file in valid:
                    pairs += 1
                    predicted = {
                        f["type"] for f in compare(valid[label["file"]], valid[expected_file])
                    }
                tp += len(predicted & expected)
                fp += len(predicted - expected)
                fn += len(expected - predicted)
    finally:
        engine.dispose()
    return {
        "comparison_pairs": pairs,
        "correct_automatic_matches": correct_matches,
        "incorrect_automatic_matches": incorrect_matches,
        "unresolved_matches": unresolved,
        "discrepancy_precision": ratio(tp, tp + fp),
        "discrepancy_recall": ratio(tp, tp + fn),
        "true_positive_findings": tp,
        "false_positive_findings": fp,
        "missed_findings": fn,
    }


def score_outputs(labels: list[dict], observations: dict[str, dict], mode: str) -> dict:
    report = {"mode": mode, "schema_version": None, "prompt_version": None}
    for scanned, group in ((False, "digital"), (True, "scanned")):
        subset = [label for label in labels if label["scanned"] == scanned]
        report[group] = score_group(subset, observations)
    # Pair every observed invoice with digital POs; don't count scan copies as competing POs.
    report["matching_and_comparison"] = score_comparisons(
        [label for label in labels if not label["scanned"]], observations
    )
    report["scanned_matching_and_comparison"] = score_comparisons(
        [
            label
            for label in labels
            if label["scanned"] or label["data"]["document_type"] == "purchase_order"
        ],
        observations,
    )
    report["cloud_cost"] = None
    report["limitation"] = (
        "Fixture results validate wiring only. Quoted-text checks do not establish "
        "semantic correctness. Recorded outputs retain the provenance you supply."
    )
    return report
