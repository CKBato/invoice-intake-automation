"""Generate synthetic invoices (three layouts) with ground truth and injected defects.

All data is fake. The seed makes every run reproducible.
"""
import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

APPROVED_VENDORS = [
    "Acme Supplies Ltd",
    "Northwind Components",
    "Blue Harbor Office Services",
    "Delta Print & Pack",
    "Keystone Maintenance Co",
    "Solaris Cleaning Services",
    "Maple Leaf Stationery",
]
UNKNOWN_VENDORS = ["Quickfix Trading", "Zephyr Holdings"]
ITEMS = ["Paper A4", "Toner cartridge", "Cleaning service", "Maintenance visit",
         "Packaging boxes", "Label rolls", "Safety gloves", "Printer repair"]
TAX_RATES = [Decimal("0.21"), Decimal("0.13"), Decimal("0.05")]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
OCR_CONFUSIONS = {"0": "O", "1": "l", "5": "S", "8": "B"}

DEFECT_WEIGHTS = [
    ("none", 0.72), ("total_mismatch", 0.08), ("missing_number", 0.06),
    ("duplicate", 0.05), ("unknown_vendor", 0.05), ("ocr_noise", 0.04),
]
HIGH_VALUE_LIMIT = Decimal("5000")


def money(d):
    return d.quantize(Decimal("0.01"))


def fmt_us(d):
    return f"{money(d):,.2f}"


def fmt_eu(d):
    return fmt_us(d).replace(",", "X").replace(".", ",").replace("X", ".")


def render(rec, layout):
    v, n = rec["vendor"], rec["invoice_number"]
    d, due = date.fromisoformat(rec["invoice_date"]), date.fromisoformat(rec["due_date"])
    lines = []
    for desc, qty, price in rec["_items"]:
        lines.append((desc, qty, price))

    if layout == "A":
        out = ["INVOICE", f"Vendor: {v}", "Phone: 555-0100"]
        if n:
            out.append(f"Invoice No: {n}")
        out += [f"Date: {d.isoformat()}", f"Due: {due.isoformat()}", ""]
        out += [f"{q} x {desc} @ {fmt_us(p)}" for desc, q, p in lines]
        out += ["", f"Subtotal: {fmt_us(Decimal(rec['subtotal']))}",
                f"Tax ({rec['_rate']}%): {fmt_us(Decimal(rec['tax']))}",
                f"Total Due: {rec['_total_text']} EUR"]
    elif layout == "B":
        out = ["FACTURA", f"Proveedor: {v}", "Tel: 600 123 456"]
        if n:
            out.append(f"Factura Nº: {n}")
        out += [f"Fecha: {d.strftime('%d/%m/%Y')}", f"Vencimiento: {due.strftime('%d/%m/%Y')}", ""]
        out += [f"{q} x {desc} @ {fmt_eu(p)}" for desc, q, p in lines]
        out += ["", f"Base imponible: {fmt_eu(Decimal(rec['subtotal']))} €",
                f"IVA ({rec['_rate']}%): {fmt_eu(Decimal(rec['tax']))} €",
                f"Importe total: {rec['_total_text']} €"]
    else:
        fmt = lambda x: f"{x.day} {MONTHS[x.month - 1]} {x.year}"
        out = ["Tax Invoice", f"Bill from: {v}", "Fax: 905-555-0199"]
        if n:
            out.append(f"Ref #: {n}")
        out += [f"Issued: {fmt(d)}", f"Due date: {fmt(due)}", ""]
        out += [f"{q} x {desc} @ ${fmt_us(p)}" for desc, q, p in lines]
        out += ["", f"Subtotal: ${fmt_us(Decimal(rec['subtotal']))}",
                f"Tax ({rec['_rate']}%): ${fmt_us(Decimal(rec['tax']))}",
                f"Amount payable: ${rec['_total_text']} CAD"]
    return "\n".join(out) + "\n"


def make_record(rng, idx, layout):
    n_items = rng.randint(1, 4)
    items = [(rng.choice(ITEMS), rng.randint(1, 10), money(Decimal(rng.randint(500, 40000)) / 100))
             for _ in range(n_items)]
    subtotal = money(sum(q * p for _, q, p in items))
    rate = rng.choice(TAX_RATES)
    tax = money(subtotal * rate)
    total = subtotal + tax
    inv_date = date(2025, 1, 1) + timedelta(days=rng.randint(0, 300))
    return {
        "vendor": rng.choice(APPROVED_VENDORS),
        "invoice_number": f"INV-{rng.randint(1000, 9999)}-{idx:03d}",
        "invoice_date": inv_date.isoformat(),
        "due_date": (inv_date + timedelta(days=rng.choice([14, 30, 45]))).isoformat(),
        "currency": {"A": "EUR", "B": "EUR", "C": "CAD"}[layout],
        "subtotal": str(subtotal),
        "tax": str(tax),
        "total": str(total),
        "_items": items,
        "_rate": str(int(rate * 100)),
        "_total_text": (fmt_eu if layout == "B" else fmt_us)(total),
    }


def generate(out_dir, n=120, seed=7):
    rng = random.Random(seed)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.txt"):
        old.unlink()
    truth, clean_pool = {}, []

    for i in range(n):
        layout = rng.choice("ABC")
        defect = rng.choices([d for d, _ in DEFECT_WEIGHTS], [w for _, w in DEFECT_WEIGHTS])[0]
        text = None

        if defect == "duplicate":
            if clean_pool:
                src_name, src_text = rng.choice(clean_pool)
                text, rec = src_text, dict(truth[src_name])
            else:
                defect = "none"
        if text is None:
            rec = make_record(rng, i, layout)
            if defect == "total_mismatch":
                wrong = Decimal(rec["total"]) + Decimal(rng.randint(5, 90))
                rec["total"] = str(money(wrong))
                rec["_total_text"] = (fmt_eu if layout == "B" else fmt_us)(wrong)
            elif defect == "missing_number":
                rec["invoice_number"] = None
            elif defect == "unknown_vendor":
                rec["vendor"] = rng.choice(UNKNOWN_VENDORS)
            text = render(rec, layout)
            if defect == "ocr_noise":
                changed = False
                new_lines = []
                for line in text.splitlines():
                    if not changed and line.startswith(("Total Due", "Importe total", "Amount payable")):
                        head, _, value = line.partition(":")
                        for k, v in OCR_CONFUSIONS.items():
                            if k in value:
                                value, changed = value.replace(k, v, 1), True
                                break
                        line = head + ":" + value
                    new_lines.append(line)
                text = "\n".join(new_lines) + "\n"
                if not changed:
                    defect = "none"

        name = f"inv_{i:03d}.txt"
        (out_dir / name).write_text(text, encoding="utf-8")
        public = {k: v for k, v in rec.items() if not k.startswith("_")}
        public["defect"] = defect
        public["expected_review"] = defect != "none" or Decimal(rec["total"]) > HIGH_VALUE_LIMIT
        public["layout"] = layout
        truth[name] = public
        if defect == "none" and not public["expected_review"]:
            clean_pool.append((name, text))

    (out_dir / "ground_truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    return truth


if __name__ == "__main__":
    import sys
    generate(sys.argv[1] if len(sys.argv) > 1 else "data/invoices")
