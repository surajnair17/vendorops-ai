import json
from copy import deepcopy

from backend.examples import examples
from backend.scripts.evaluate import evaluate
from backend.services.evaluation import character_error_rate, score_outputs


def labels_and_outputs():
    order, invoice = examples()[3:5]
    labels = [
        dict(order, file="PO-002.pdf", scanned=False),
        dict(
            invoice,
            file="INV-002.pdf",
            scanned=False,
            expected_po_file="PO-002.pdf",
            expected_findings=["price_variance"],
        ),
    ]
    observations = {
        label["file"]: {"structured": label["data"], "pages": [label["text"]]} for label in labels
    }
    return labels, observations


def test_fixture_scoring_uses_real_matching_and_finding_logic():
    labels, observations = labels_and_outputs()
    result = score_outputs(labels, observations, "fixture_plumbing_only")
    assert result["digital"]["critical_field_accuracy"] == 1
    assert result["digital"]["line_item_field_accuracy"] == 1
    assert result["digital"]["citation_quote_accuracy"] == 1
    assert result["matching_and_comparison"]["correct_automatic_matches"] == 1
    assert result["matching_and_comparison"]["discrepancy_recall"] == 1


def test_failed_documents_stay_in_denominator_and_missed_findings_count():
    labels, observations = labels_and_outputs()
    observations.pop("INV-002.pdf")
    result = score_outputs(labels, observations, "test")
    assert result["digital"]["critical_field_accuracy"] == 0.5
    assert result["digital"]["completion_rate"] == 0.5
    assert result["schema_version"] is None
    assert result["prompt_version"] is None
    assert result["matching_and_comparison"]["discrepancy_recall"] == 0
    assert result["matching_and_comparison"]["unresolved_matches"] == 1


def test_extra_items_wrong_values_and_bad_citations_reduce_scores():
    labels, observations = labels_and_outputs()
    observations = deepcopy(observations)
    actual = observations["INV-002.pdf"]["structured"]
    actual["items"].append({**actual["items"][0], "item_id": "unexpected"})
    actual["currency"] = "EUR"
    actual["evidence"]["currency"]["page"] = 99
    result = score_outputs(labels, observations, "test")
    assert result["digital"]["critical_field_accuracy"] < 1
    assert result["digital"]["line_item_field_accuracy"] < 1
    assert result["digital"]["unsupported_citations"] == 1


def test_ocr_edit_distance_and_scanned_group_are_independent():
    assert character_error_rate("invoice", "invo1ce") == 1 / 7
    assert character_error_rate("hello\nworld", "hello world") == 0
    labels, observations = labels_and_outputs()
    labels[1]["scanned"] = True
    result = score_outputs(labels, observations, "recorded:stub")
    assert result["scanned"]["documents"] == 1
    assert result["scanned"]["ocr_character_error_rate"] == 0
    assert result["digital"]["documents"] == 1


def test_recorded_run_scores_missing_documents_in_selected_split(tmp_path):
    labels, observations = labels_and_outputs()
    for label in labels:
        label["split"] = "test"
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(labels), encoding="utf-8")
    observations.pop("INV-002.pdf")
    saved = tmp_path / "results.json"
    saved.write_text(
        json.dumps(
            {"provider": "stub", "split": "test", "include_scans": False, "documents": observations}
        ),
        encoding="utf-8",
    )
    result = evaluate(manifest, results_path=saved)
    assert result["digital"]["documents"] == 2
    assert result["digital"]["completion_rate"] == 0.5
    assert result["schema_version"] is None
    assert result["prompt_version"] is None
    saved_data = json.loads(saved.read_text(encoding="utf-8"))
    saved_data.update({"schema_version": 1, "prompt_version": 1, "model_id": "recorded-model"})
    saved.write_text(json.dumps(saved_data), encoding="utf-8")
    result = evaluate(manifest, results_path=saved)
    assert result["schema_version"] == 1
    assert result["prompt_version"] == 1
    assert result["model_id"] == "recorded-model"
