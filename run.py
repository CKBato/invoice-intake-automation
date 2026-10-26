"""One command: generate synthetic invoices, run the pipeline, print the evaluation."""
import json
import sys
from pathlib import Path

from intake.evaluate import evaluate_dir
from intake.generate import generate
from intake.pipeline import process_dir

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "invoices"
OUT = ROOT / "output"


def main(n=120, seed=7):
    generate(DATA, n=n, seed=seed)
    results = process_dir(DATA, OUT)
    report = evaluate_dir(OUT, DATA / "ground_truth.json")
    (OUT / "evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    review = sum(r["decision"] == "review" for r in results)
    print(f"\n{len(results)} documents: {len(results) - review} auto-approved, {review} sent to review "
          f"(see output/review_queue.csv)")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:3]))
