"""Business rules. Each failed rule becomes a reason code shown to the reviewer."""
import re
from decimal import Decimal

REQUIRED = ["vendor", "invoice_number", "invoice_date", "due_date", "subtotal", "tax", "total"]
MIN_CONFIDENCE = 0.80
HIGH_VALUE_LIMIT = Decimal("5000")
TOTAL_TOLERANCE = Decimal("0.01")


def normalize_vendor(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def validate(fields, approved_vendors, seen_keys):
    """fields: {name: (value, confidence)}. seen_keys: set of (vendor, number) already processed."""
    reasons = []
    for f in REQUIRED:
        value, conf = fields[f]
        if value is None:
            reasons.append(f"MISSING_FIELD:{f}")
        elif conf < MIN_CONFIDENCE:
            reasons.append(f"LOW_CONFIDENCE:{f}")

    vendor, number = fields["vendor"][0], fields["invoice_number"][0]
    if vendor and normalize_vendor(vendor) not in {normalize_vendor(v) for v in approved_vendors}:
        reasons.append("UNKNOWN_VENDOR")

    if vendor and number:
        key = (normalize_vendor(vendor), number)
        if key in seen_keys:
            reasons.append("DUPLICATE")
        seen_keys.add(key)

    try:
        sub, tax, total = (Decimal(fields[f][0]) for f in ("subtotal", "tax", "total"))
        if abs(sub + tax - total) > TOTAL_TOLERANCE:
            reasons.append("TOTAL_MISMATCH")
        if total > HIGH_VALUE_LIMIT:
            reasons.append("HIGH_VALUE")
    except (TypeError, ValueError, ArithmeticError):
        pass  # already reported as MISSING_FIELD

    inv, due = fields["invoice_date"][0], fields["due_date"][0]
    if inv and due and due < inv:
        reasons.append("DUE_BEFORE_INVOICE")
    return reasons
