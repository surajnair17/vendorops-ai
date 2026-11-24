import json

from backend.scripts.evaluate_ocr import edit_distance, evaluate


def test_ocr_metric_counts_insertions_deletions_and_substitutions():
    assert edit_distance("ABC", "ABC") == 0
    assert edit_distance("ABC", "AXC") == 1
    assert edit_distance("ABC", "ABCD") == 1
    assert edit_distance("ABC", "AC") == 1
    assert edit_distance("", "ABC") == 3


def test_ocr_benchmark_uses_held_out_scans_and_reports_failures(tmp_path, monkeypatch):
    labels = [
        {"file": "held-scan.pdf", "scanned": True, "split": "test", "text": "ABC"},
        {"file": "broken-scan.pdf", "scanned": True, "split": "test", "text": "ABC"},
        {"file": "training.pdf", "scanned": True, "split": "dev", "text": "ABC"},
        {"file": "digital.pdf", "scanned": False, "split": "test", "text": "ABC"},
    ]
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(labels), encoding="utf-8")
    (tmp_path / "held-scan.pdf").write_bytes(b"synthetic")
    monkeypatch.setattr("backend.scripts.evaluate_ocr.extract_pages", lambda content: [""])
    monkeypatch.setattr("backend.scripts.evaluate_ocr.recognize_pages", lambda *args: [["AXC"]])
    result = evaluate(manifest)
    assert result["document_count"] == 2
    assert result["failed_documents"] == 1
    assert result["character_error_rate_completed_only"] == 1 / 3
