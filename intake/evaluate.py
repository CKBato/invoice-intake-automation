"""Score the pipeline against ground truth."""
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from .extract import FIELDS


def _same(field, got, want):
    if got is None or want is None:
        return got is want
    if field in ("subtotal", "tax", "total"):
        return Decimal(got) == Decimal(want)
    return got == want


def evaluate(results, truth):
    n = len(results)
    correct = Counter()
    auto = [r for r in results if r["decision"] == "auto_approved"]
    defective = [r for r in results if truth[r["file"]]["defect"] != "none"]
    expected_review = [r for r in results if truth[r["file"]]["expected_review"]]
    clean = [r for r in results if not truth[r["file"]]["expected_review"]]

    for r in results:
        t = truth[r["file"]]
        for f in FIELDS:
            correct[f] += _same(f, r["fields"][f], t[f])

    bad_auto = [r["file"] for r in auto if truth[r["file"]]["expected_review"]]
    caught = [r for r in expected_review if r["decision"] == "review"]
    false_review = [r for r in clean if r["decision"] == "review"]
    wrong_auto_fields = [r["file"] for r in auto
                         if not all(_same(f, r["fields"][f], truth[r["file"]][f]) for f in FIELDS)]

    by_defect = Counter()
    caught_by_defect = Counter()
    for r in defective:
        d = truth[r["file"]]["defect"]
        by_defect[d] += 1
        caught_by_defect[d] += r["decision"] == "review"

    return {
        "documents": n,
        "field_accuracy": {f: round(correct[f] / n, 3) for f in FIELDS},
        "straight_through_rate": round(len(auto) / n, 3),
        "needs_review_expected": len(expected_review),
        "needs_review_caught": len(caught),
        "review_recall": round(len(caught) / len(expected_review), 3) if expected_review else None,
        "bad_auto_approvals": bad_auto,
        "auto_approved_with_wrong_fields": wrong_auto_fields,
        "false_review_rate_on_clean_docs": round(len(false_review) / len(clean), 3) if clean else None,
        "defect_catch": {d: f"{caught_by_defect[d]}/{by_defect[d]}" for d in sorted(by_defect)},
    }


def evaluate_dir(out_dir, truth_path):
    results = json.loads((Path(out_dir) / "results.json").read_text(encoding="utf-8"))
    truth = json.loads(Path(truth_path).read_text(encoding="utf-8"))
    return evaluate(results, truth)
