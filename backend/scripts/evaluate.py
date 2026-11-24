"""Evaluate fixtures, held-out live digital documents, or saved digital/OCR outputs."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from backend.config import settings
from backend.services.evaluation import score_outputs
from backend.services.pdf_extractor import extract_pages
from backend.services.structured import extract_structure


def evaluate(manifest_path: Path, live: bool = False, results_path: Path | None = None) -> dict:
    labels = json.loads(manifest_path.read_text(encoding="utf-8"))
    if results_path:
        saved = json.loads(results_path.read_text(encoding="utf-8"))
        split = saved.get("split", "test")
        if split not in {"dev", "test", "all"}:
            raise ValueError("Recorded result split must be dev, test, or all.")
        selected = [
            label
            for label in labels
            if (split == "all" or label["split"] == split)
            and (saved.get("include_scans", True) or not label["scanned"])
        ]
        return score_outputs(selected, saved["documents"], f"recorded:{saved['provider']}")
    if live and settings.provider != "bedrock":
        raise ValueError(
            "Live evaluation requires the bedrock provider and live-call configuration."
        )
    if not live and settings.provider != "fixture":
        raise ValueError("Offline evaluation requires the fixture provider.")
    selected = [
        label for label in labels if not label["scanned"] and (not live or label["split"] == "test")
    ]
    observations = {}
    for label in selected:
        started = perf_counter()
        try:
            pages = extract_pages((manifest_path.parent / label["file"]).read_bytes())
            result = extract_structure("\n\n".join(pages), pages)
            observations[label["file"]] = {"pages": pages, "structured": result["structured"]}
        except Exception as error:
            observations[label["file"]] = {
                "error_code": getattr(error, "code", type(error).__name__)
            }
        observations[label["file"]]["latency_seconds"] = perf_counter() - started
    mode = "live_model" if live else "fixture_plumbing_only"
    report = score_outputs(selected, observations, mode)
    report["model_id"] = settings.model_id if live else None
    report["scanned"]["note"] = (
        "Supply --results with recorded OCR text and structured outputs to score scans."
    )
    report["source_manifest"] = str(manifest_path)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--manifest", type=Path, default=Path("backend/artifacts/samples/manifest.json")
    )
    parser.add_argument("--output", type=Path, default=Path("backend/artifacts/evaluation.json"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Paid held-out digital extraction")
    mode.add_argument(
        "--results", type=Path, help="Score saved observations without invoking services"
    )
    args = parser.parse_args()
    result = evaluate(args.manifest, args.live, args.results)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
