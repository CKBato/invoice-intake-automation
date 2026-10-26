# Invoice Intake Automation (portfolio demo)

Turn a pile of semi-structured invoices into clean records, auto-approve the safe ones, and send everything doubtful to a human with a reason attached. Runs offline with Python's standard library only. All data is synthetic.

## The problem
Accounts-payable teams retype invoice data by hand. The risk is not the typing, it is the errors that slip through: wrong totals, duplicate invoices, unknown vendors, missing numbers. Automation that guesses silently makes this worse. The goal here is **safe** automation: do the easy ones automatically, and never approve something it is unsure about.

## How it works
```
invoice (.txt) -> extract (fields + confidence) -> validate (business rules) -> route
                                                                   |-> auto-approved -> SQLite
                                                                   |-> review queue (CSV, with reason codes)
                                                   every decision -> audit.jsonl
```
- **Extract** (`intake/extract.py`): pulls vendor, invoice number, dates, subtotal, tax, total, currency. Handles US and European number formats and three invoice layouts (English, Spanish, Canadian). Each field carries a confidence; fallbacks are deliberately low-confidence.
- **Validate** (`intake/validate.py`): missing fields, low confidence, unknown vendor, duplicate, subtotal + tax != total, due date before invoice date, high-value (> 5,000) always reviewed.
- **Route + record** (`intake/pipeline.py`): auto-approve only when every rule passes. Writes `results.json`, `invoices.db` (SQLite), `review_queue.csv`, `audit.jsonl`.
- **Evaluate** (`intake/evaluate.py`): scores against ground truth, including the failure that matters most: defective invoices that were auto-approved.

The extractor is a swappable layer. An LLM-based extractor can replace `extract()` as long as it returns the same `{field: (value, confidence)}` shape, and everything downstream stays the same. I have **not** built or tested an LLM extractor here.

## Run it
```bash
python ui.py                   # local web UI at http://127.0.0.1:8765
```
The UI has two tabs: paste or open a single invoice and see each field with its confidence and the reason codes, or generate a batch and work the review queue with Approve / Reject (decisions are logged to `output/reviewer_decisions.jsonl`). It binds to localhost only.

```bash
python run.py                  # generate 120 synthetic invoices, process, print evaluation
python -m unittest discover -s tests -t .
```

## Results (120 synthetic invoices, seed 7)
| Metric | Result |
|---|---|
| Field accuracy (7 of 8 fields) | 100% |
| Field accuracy: total | 95% (the misses are the injected OCR-garbled totals) |
| Straight-through (auto-approved) | 56.7% |
| Documents that should go to review | 52 |
| ...of which sent to review | 52 (100%) |
| Defective or risky invoices auto-approved | 0 |
| Clean invoices sent to review needlessly | 0% |

Defects caught: total mismatch 14/14, unknown vendor 10/10, missing number 8/8, OCR-garbled total 6/6, duplicate 1/1. Seeds 1, 2 and 3 gave 58-59% straight-through, 100% review recall and no bad auto-approvals.

## Honest limits
- **These numbers are a best case.** I wrote the generator and the extractor together, so the extractor knows all three layouts. Real invoices (scanned PDFs, other layouts, other languages) will score lower. The meaningful result is the safety behavior, not the accuracy.
- A test (`test_unseen_layout_fails_safe`) shows an unfamiliar layout goes to review instead of being auto-approved.
- The duplicate count is small (1) in the default seed, so that rate says little.
- Input is plain text. A real deployment needs PDF/image OCR first, with its own accuracy to measure.
- The straight-through rate is low by design: high-value invoices are always reviewed, and the 5,000 limit is an arbitrary example.

## What a real engagement adds
1. Measure on 50-100 of the client's real (redacted) invoices before promising anything.
2. OCR or document-AI step for scans, and an LLM extractor for layout variety, evaluated with the same harness.
3. Reviewer UI instead of a CSV, and write-back to the client's ERP or accounting system.
4. Tuned thresholds and rules, with a human sign-off policy agreed with finance.
5. Monitoring: accuracy drift, review volume, time saved.

## Files
`run.py`, `ui.py`, `intake/` (generate, extract, validate, pipeline, evaluate), `tests/`. `data/` and `output/` are regenerated on each run.
