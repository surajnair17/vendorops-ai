"""Measure real offline Tesseract output against labelled scanned synthetic PDFs."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from backend.services.local_ocr import recognize_pages
from backend.services.pdf_extractor import extract_pages


def edit_distance(expected: str, actual: str) -> int:
    previous = list(range(len(actual) + 1))
    for row, left in enumerate(expected, 1):
        current = [row]
        for column, right in enumerate(actual, 1):
            current.append(
                min(current[-1] + 1, previous[column] + 1, previous[column - 1] + (left != right))
            )
        previous = current
    return previous[-1]


def evaluate(manifest: Path, split: str = "test") -> dict:
    labels = json.loads(manifest.read_text(encoding="utf-8"))
    observations = {}
    total_characters = total_errors = 0
    failures = 0
    for label in labels:
        if not label["scanned"] or split != "all" and label["split"] != split:
            continue
        started = perf_counter()
        expected = " ".join(label["text"].split())
        try:
            path = manifest.parent / label["file"]
            original = extract_pages(path.read_bytes())
            pages = recognize_pages(path, original)
            actual = " ".join(" ".join("\n".join(page) for page in pages).split())
            distance = edit_distance(expected, actual)
            total_characters += len(expected)
            total_errors += distance
            observations[label["file"]] = {
                "pages": ["\n".join(page) for page in pages],
                "character_errors": distance,
                "reference_characters": len(expected),
            }
        except Exception as error:
            failures += 1
            observations[label["file"]] = {
                "error_code": getattr(error, "code", type(error).__name__)
            }
        observations[label["file"]]["latency_seconds"] = perf_counter() - started
    return {
        "provider": "local_tesseract",
        "split": split,
        "include_scans": True,
        "documents": observations,
        "document_count": len(observations),
        "failed_documents": failures,
        "reference_characters_scored": total_characters,
        "character_error_rate_completed_only": total_errors / total_characters
        if total_characters
        else None,
        "normalization": "Collapse whitespace; keep case/punctuation; exact Levenshtein distance.",
        "limitation": "Synthetic scans only; failures reported separately; no model accuracy claim",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("backend/artifacts/samples/manifest.json")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("backend/artifacts/ocr-evaluation.json")
    )
    parser.add_argument("--split", choices=["dev", "test", "all"], default="test")
    args = parser.parse_args()
    result = evaluate(args.manifest, args.split)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "documents"}, indent=2))
    if result["failed_documents"] or not result["document_count"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
