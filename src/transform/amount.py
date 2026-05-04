"""
Transformation engine for the Amount concept.

Reads:
  data/raw/*.csv         (synthetic SSBTEK source data, at project root)
  src/mappings/amount.json (declarative rules)

Run from the project root:
  python -m src.transform.amount
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from src.models.amount import Frequency, MonetaryAmount, ValueContext

# ── Paths anchored to the project root ────────────────────────────────────────
# This file lives at  mapping-copilot/src/transform/amount.py
# so the project root is THREE parents up.
PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent
DATA_DIR      = PROJECT_ROOT / "data" / "raw"
MAPPINGS_FILE = PROJECT_ROOT / "src" / "mappings" / "amount.json"

JANE_PNR = "20000421-1234"


# ── Loading ───────────────────────────────────────────────────────────────────

def load_mappings(path: Path = MAPPINGS_FILE) -> list[dict]:
    """Return the list of rules from the mapping spec file."""
    return json.loads(path.read_text(encoding="utf-8"))["rules"]


def _safe_decimal(s: str) -> Decimal | None:
    """Parse a CSV cell as Decimal, returning None on empty/invalid."""
    if s is None or s == "":
        return None
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


# ── Core transformation ───────────────────────────────────────────────────────

def transform_amount(personal_id: str,
                     mappings: list[dict] | None = None,
                     data_dir: Path = DATA_DIR) -> list[MonetaryAmount]:
    """
    Apply all Amount-targeting mappings to one person's source data
    and return a list of MonetaryAmount instances.
    """
    if mappings is None:
        mappings = load_mappings()

    # Group rules by source file so each CSV is opened once
    rules_by_file: dict[str, list[dict]] = defaultdict(list)
    for rule in mappings:
        rules_by_file[rule["source_file"]].append(rule)

    amounts: list[MonetaryAmount] = []

    for filename, rules in rules_by_file.items():
        path = data_dir / filename
        if not path.exists():
            print(f"  ⚠  {filename} not found at {path} — skipping")
            continue

        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row_idx, row in enumerate(reader):
                if row.get("personal_id") != personal_id:
                    continue

                for rule in rules:
                    field = rule["source_field"]
                    raw   = row.get(field)
                    value = _safe_decimal(raw)
                    if value is None:
                        continue

                    amounts.append(MonetaryAmount(
                        value=value,
                        currency=rule.get("currency", "SEK"),
                        frequency=Frequency(rule["frequency"]),
                        context=(ValueContext(rule["context"])
                                 if rule.get("context") else None),
                        source_file=filename,
                        source_field=field,
                        source_record_id=f"row{row_idx}",
                    ))

    return amounts


# ── Aggregation helpers ───────────────────────────────────────────────────────

def sum_by(amounts: list[MonetaryAmount],
           source_file: str | None = None,
           frequency: Frequency | None = None,
           context: ValueContext | None = None) -> Decimal:
    """Sum amounts after optional filtering."""
    selected = amounts
    if source_file is not None:
        selected = [a for a in selected if a.source_file == source_file]
    if frequency is not None:
        selected = [a for a in selected if a.frequency == frequency]
    if context is not None:
        selected = [a for a in selected if a.context == context]
    return sum((a.value for a in selected), Decimal(0))


# ── Demo: walk Jane's amounts end-to-end ──────────────────────────────────────

def demo_jane() -> None:
    print("=" * 64)
    print(f"  Resolving Amount concept for {JANE_PNR} (Jane Doe)")
    print("=" * 64)
    print()
    print(f"  Project root: {PROJECT_ROOT}")
    print(f"  Data dir:     {DATA_DIR}")
    print(f"  Mappings:     {MAPPINGS_FILE}")
    print()

    amounts = transform_amount(JANE_PNR)

    if not amounts:
        print("  No amounts found. Did you run synthetic.py first?")
        print(f"  Expected CSVs in: {DATA_DIR}")
        return

    print(f"Found {len(amounts)} MonetaryAmount instance(s):\n")

    by_file: dict[str, list[MonetaryAmount]] = defaultdict(list)
    for a in amounts:
        by_file[a.source_file].append(a)

    for filename, items in by_file.items():
        print(f"  {filename}  ({len(items)} value(s))")
        for a in items:
            print(f"    [{a.source_field:25s} from {a.source_record_id:8s}] "
                  f"= {a}")
        print()

    print("─" * 64)
    print("AGGREGATES")
    print("─" * 64)

    fk_net_total   = sum_by(amounts, "fk_payment.csv",
                            context=ValueContext.NET)
    fk_gross_total = sum_by(amounts, "fk_payment.csv",
                            context=ValueContext.GROSS)
    csn_per_type_totals = sum_by(amounts, "csn_approved_amounts.csv",
                                 frequency=Frequency.TOTAL)
    grand = fk_net_total + csn_per_type_totals

    print(f"  FK Aktivitetsstöd (net, sum of monthly payments):  "
          f"{fk_net_total:>10,.0f} SEK")
    print(f"  FK Aktivitetsstöd (gross, sum of monthly payments):"
          f" {fk_gross_total:>10,.0f} SEK")
    print(f"  CSN study aid (sum of grant + loan totals):        "
          f"{csn_per_type_totals:>10,.0f} SEK")
    print(f"  Combined total expected:                           "
          f"{grand:>10,.0f} SEK")
    print()

    print("─" * 64)
    print("VERIFICATION against demo expected values")
    print("─" * 64)
    checks = [
        ("FK Aktivitetsstöd net",     fk_net_total,        Decimal("29120")),
        ("FK Aktivitetsstöd gross",   fk_gross_total,      Decimal("36400")),
        ("CSN total (grant + loan)",  csn_per_type_totals, Decimal("18689")),
        ("Combined (FK net + CSN)",   grand,               Decimal("47809")),
    ]
    for label, actual, expected in checks:
        ok = "✓" if actual == expected else "✗"
        print(f"  {ok}  {label:30s} actual={actual:>8,.0f}  "
              f"expected={expected:>8,.0f}")


if __name__ == "__main__":
    demo_jane()