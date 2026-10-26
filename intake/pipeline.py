"""Extract -> validate -> route. Writes results, SQLite, review queue and audit log."""
import csv
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .extract import FIELDS, extract
from .generate import APPROVED_VENDORS
from .validate import validate


def process_dir(input_dir, out_dir, approved_vendors=None):
    approved_vendors = approved_vendors or APPROVED_VENDORS
    input_dir, out_dir = Path(input_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    seen, results = set(), []
    for path in sorted(input_dir.glob("*.txt")):
        fields = extract(path.read_text(encoding="utf-8"))
        reasons = validate(fields, approved_vendors, seen)
        results.append({
            "file": path.name,
            "fields": {f: fields[f][0] for f in FIELDS},
            "confidence": {f: fields[f][1] for f in FIELDS},
            "decision": "review" if reasons else "auto_approved",
            "reasons": reasons,
        })

    _write_outputs(results, out_dir)
    return results


def _write_outputs(results, out_dir):
    (out_dir / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    with open(out_dir / "review_queue.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "vendor", "invoice_number", "total", "reasons"])
        for r in results:
            if r["decision"] == "review":
                f = r["fields"]
                w.writerow([r["file"], f["vendor"], f["invoice_number"], f["total"], ";".join(r["reasons"])])

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(out_dir / "audit.jsonl", "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps({"ts": now, "file": r["file"], "decision": r["decision"],
                                 "reasons": r["reasons"], "extracted": r["fields"]}) + "\n")

    db_path = out_dir / "invoices.db"
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    con.execute("""CREATE TABLE invoices (file TEXT PRIMARY KEY, vendor TEXT, invoice_number TEXT,
                   invoice_date TEXT, due_date TEXT, currency TEXT, subtotal TEXT, tax TEXT,
                   total TEXT, status TEXT, reasons TEXT)""")
    for r in results:
        f = r["fields"]
        con.execute("INSERT INTO invoices VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (r["file"], f["vendor"], f["invoice_number"], f["invoice_date"], f["due_date"],
                     f["currency"], f["subtotal"], f["tax"], f["total"], r["decision"],
                     ";".join(r["reasons"])))
    con.commit()
    con.close()
