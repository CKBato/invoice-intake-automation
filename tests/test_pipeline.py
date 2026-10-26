import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from intake.evaluate import evaluate
from intake.extract import extract, parse_amount
from intake.generate import generate
from intake.pipeline import process_dir
from intake.validate import validate

VENDORS = ["Acme Supplies Ltd"]
GOOD = {
    "vendor": ("Acme Supplies Ltd", 0.95), "invoice_number": ("INV-1", 0.95),
    "invoice_date": ("2025-03-01", 0.95), "due_date": ("2025-03-31", 0.95),
    "currency": ("EUR", 0.95), "subtotal": ("100.00", 0.95),
    "tax": ("21.00", 0.95), "total": ("121.00", 0.95),
}


class ParseAmount(unittest.TestCase):
    def test_us_and_eu_formats(self):
        self.assertEqual(parse_amount("1,452.00 EUR"), Decimal("1452.00"))
        self.assertEqual(parse_amount("1.452,00 €"), Decimal("1452.00"))
        self.assertEqual(parse_amount("$12,345.67 CAD"), Decimal("12345.67"))

    def test_garbled_amount_is_rejected_not_guessed(self):
        self.assertIsNone(parse_amount("1,4S2.15"))
        self.assertIsNone(parse_amount("1,452.1O"))


class Validate(unittest.TestCase):
    def test_clean_invoice_has_no_reasons(self):
        self.assertEqual(validate(GOOD, VENDORS, set()), [])

    def test_total_mismatch(self):
        bad = {**GOOD, "total": ("150.00", 0.95)}
        self.assertIn("TOTAL_MISMATCH", validate(bad, VENDORS, set()))

    def test_duplicate_is_flagged_on_second_sight(self):
        seen = set()
        self.assertEqual(validate(GOOD, VENDORS, seen), [])
        self.assertIn("DUPLICATE", validate(GOOD, VENDORS, seen))

    def test_unknown_vendor_and_low_confidence(self):
        bad = {**GOOD, "vendor": ("Mystery Co", 0.95), "total": ("121.00", 0.6)}
        reasons = validate(bad, VENDORS, set())
        self.assertIn("UNKNOWN_VENDOR", reasons)
        self.assertIn("LOW_CONFIDENCE:total", reasons)

    def test_due_before_invoice(self):
        bad = {**GOOD, "due_date": ("2025-02-01", 0.95)}
        self.assertIn("DUE_BEFORE_INVOICE", validate(bad, VENDORS, set()))


class EndToEnd(unittest.TestCase):
    def test_generated_set_nothing_defective_is_auto_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            data, out = Path(tmp) / "in", Path(tmp) / "out"
            truth = generate(data, n=80, seed=11)
            results = process_dir(data, out)
            report = evaluate(results, truth)
            self.assertEqual(report["bad_auto_approvals"], [])
            self.assertEqual(report["auto_approved_with_wrong_fields"], [])
            self.assertTrue((out / "review_queue.csv").exists())
            self.assertTrue((out / "invoices.db").exists())

    def test_unseen_layout_fails_safe(self):
        """A layout the extractor was never built for must go to review, never auto-approve."""
        unseen = "Rechnung\nLieferant = Acme Supplies Ltd\nNr 4471\nSumme 121,00 EUR\n"
        with tempfile.TemporaryDirectory() as tmp:
            data, out = Path(tmp) / "in", Path(tmp) / "out"
            data.mkdir()
            (data / "odd.txt").write_text(unseen, encoding="utf-8")
            results = process_dir(data, out)
            self.assertEqual(results[0]["decision"], "review")
            self.assertTrue(any(r.startswith("MISSING_FIELD") for r in results[0]["reasons"]))


if __name__ == "__main__":
    unittest.main()
