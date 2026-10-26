"""Rule-based field extraction with per-field confidence.

This is the swappable layer: an LLM extractor can replace extract() as long as it
returns the same {field: (value, confidence)} shape. Everything downstream
(validation, routing, audit) stays unchanged.
"""
import re
from datetime import datetime
from decimal import Decimal

FIELDS = ["vendor", "invoice_number", "invoice_date", "due_date",
          "currency", "subtotal", "tax", "total"]

PRIMARY = 0.95
FALLBACK = 0.60

LABELS = {
    "vendor": r"(?:vendor|supplier|bill from|proveedor)",
    "invoice_number": r"(?:invoice\s*(?:no\.?|number|#)|factura\s*n[º°o]\.?|ref\s*#?)",
    "invoice_date": r"(?:invoice\s*date|date|fecha|issued)",
    "due_date": r"(?:due(?:\s*date)?|vencimiento)",
    "subtotal": r"(?:subtotal|base imponible)",
    "tax": r"(?:tax|vat|iva)[^:\n]*",
    "total": r"(?:total(?:\s*due)?|amount payable|importe total)",
}

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%d %B %Y"]
AMOUNT_RE = re.compile(r"\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?|\d+(?:[.,]\d{2})?")
CURRENCY_WORDS = re.compile(r"EUR|USD|CAD|GBP|[€$£]", re.I)


def _line_value(text, label):
    m = re.search(rf"(?im)^\s*{label}\s*[:\-]\s*(.+?)\s*$", text)
    return m.group(1) if m else None


def parse_amount(s):
    """Parse '1,452.00', '1.452,00', '$1,452.00 CAD'. Return Decimal or None if not clean."""
    cleaned = CURRENCY_WORDS.sub("", s).strip()
    if not AMOUNT_RE.fullmatch(cleaned):
        return None
    last = max(cleaned.rfind(","), cleaned.rfind("."))
    if last != -1 and re.fullmatch(r"\d{2}", cleaned[last + 1:]):
        whole, frac = cleaned[:last], cleaned[last + 1:]
    else:
        whole, frac = cleaned, "00"
    whole = re.sub(r"[.,]", "", whole)
    return Decimal(f"{whole}.{frac}")


def parse_date(s):
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _currency(total_line, text):
    for source in (total_line or "", text):
        if "€" in source or re.search(r"\bEUR\b", source):
            return "EUR"
        if re.search(r"\bCAD\b", source):
            return "CAD"
        if "£" in source or re.search(r"\bGBP\b", source):
            return "GBP"
        if "$" in source or re.search(r"\bUSD\b", source):
            return "USD"
    return None


def extract(text):
    out = {f: (None, 0.0) for f in FIELDS}

    v = _line_value(text, LABELS["vendor"])
    if v:
        out["vendor"] = (v, PRIMARY)

    n = _line_value(text, LABELS["invoice_number"])
    if n and re.fullmatch(r"[A-Za-z0-9\-/]+", n):
        out["invoice_number"] = (n, PRIMARY)

    for f in ("invoice_date", "due_date"):
        raw = _line_value(text, LABELS[f])
        parsed = parse_date(raw) if raw else None
        if parsed:
            out[f] = (parsed, PRIMARY)

    for f in ("subtotal", "tax"):
        raw = _line_value(text, LABELS[f])
        amount = parse_amount(raw) if raw else None
        if amount is not None:
            out[f] = (str(amount), PRIMARY)

    total_raw = _line_value(text, LABELS["total"])
    total = parse_amount(total_raw) if total_raw else None
    if total is not None:
        out["total"] = (str(total), PRIMARY)
    else:
        # Fallback: largest clean amount anywhere in the document. Low confidence on purpose.
        candidates = [parse_amount(t) for t in re.findall(r"\d[\d.,]*\d", text)]
        candidates = [c for c in candidates if c is not None]
        if candidates:
            out["total"] = (str(max(candidates)), FALLBACK)

    currency = _currency(total_raw, text)
    if currency:
        out["currency"] = (currency, PRIMARY)
    return out
