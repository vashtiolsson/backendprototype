"""
Transformation engine for the TimePeriod concept.

Reads:
  data/raw/*.csv          synthetic SSBTEK source data, at project root
  src/mappings/time.json  declarative TimePeriod rules

Run from the project root:
  python -m src.transform.period
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from src.models.period import TimeFormat, TimePeriod


PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent
DATA_DIR      = PROJECT_ROOT / "data" / "raw"
MAPPINGS_FILE = PROJECT_ROOT / "src" / "mappings" / "period.json"

JANE_PNR = "20000421-1234"


# ── Loading ───────────────────────────────────────────────────────────────────

def load_mappings(path: Path = MAPPINGS_FILE) -> list[dict]:
    """Return the list of rules from the mapping spec file."""
    return json.loads(path.read_text(encoding="utf-8"))["rules"]


# ── Date parsing ──────────────────────────────────────────────────────────────

def _safe_date(value: str | None, fmt: TimeFormat) -> date | None:
    """Parse a source date/week value into a normalized Python date."""
    if value is None or value == "":
        return None

    value = str(value).strip()

    try:
        if fmt == TimeFormat.DATE:
            return datetime.strptime(value, "%Y-%m-%d").date()

        if fmt == TimeFormat.COMPACT_DATE:
            return datetime.strptime(value, "%Y%m%d").date()

        if fmt == TimeFormat.YEAR_WEEK:
            year = int(value[:4])
            week = int(value[4:6])
            return date.fromisocalendar(year, week, 1)

    except (ValueError, TypeError):
        return None

    return None


def _safe_period_end(value: str | None, fmt: TimeFormat) -> date | None:
    """Parse an end value. For YearWeek, return the Sunday of that ISO week."""
    if value is None or value == "":
        return None

    value = str(value).strip()

    try:
        if fmt == TimeFormat.YEAR_WEEK:
            year = int(value[:4])
            week = int(value[4:6])
            return date.fromisocalendar(year, week, 7)

        return _safe_date(value, fmt)

    except (ValueError, TypeError):
        return None


# ── Core transformation ───────────────────────────────────────────────────────

def transform_period(
    personal_id: str,
    mappings: list[dict] | None = None,
    data_dir: Path = DATA_DIR,
) -> list[TimePeriod]:
    """
    Apply all TimePeriod-targeting mappings to one person's source data
    and return a list of TimePeriod instances.
    """
    if mappings is None:
        mappings = load_mappings()

    rules_by_file: dict[str, list[dict]] = defaultdict(list)
    for rule in mappings:
        rules_by_file[rule["source_file"]].append(rule)

    periods: list[TimePeriod] = []

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
                    fmt = TimeFormat(rule["format"])

                    start_field = rule["start_field"]
                    end_field = rule.get("end_field")

                    start_date = _safe_date(row.get(start_field), fmt)
                    end_date = (
                        _safe_period_end(row.get(end_field), fmt)
                        if end_field
                        else None
                    )

                    if start_date is None:
                        continue

                    periods.append(TimePeriod(
                        start_date=start_date,
                        end_date=end_date,
                        source_format=fmt,
                        source_file=filename,
                        source_start_field=start_field,
                        source_end_field=end_field,
                        source_record_id=f"row{row_idx}",
                    ))

    return periods


# ── Demo: walk Jane's periods end-to-end ──────────────────────────────────────

def demo_jane() -> None:
    print("=" * 64)
    print(f"  Resolving TimePeriod concept for {JANE_PNR} (Jane Doe)")
    print("=" * 64)
    print()
    print(f"  Project root: {PROJECT_ROOT}")
    print(f"  Data dir:     {DATA_DIR}")
    print(f"  Mappings:     {MAPPINGS_FILE}")
    print()

    periods = transform_period(JANE_PNR)

    if not periods:
        print("  No periods found. Did you run synthetic.py first?")
        print(f"  Expected CSVs in: {DATA_DIR}")
        return

    print(f"Found {len(periods)} TimePeriod instance(s):\n")

    by_file: dict[str, list[TimePeriod]] = defaultdict(list)
    for period in periods:
        by_file[period.source_file].append(period)

    for filename, items in by_file.items():
        print(f"  {filename}  ({len(items)} period(s))")
        for p in items:
            end_field = p.source_end_field or "None"
            print(
                f"    [{p.source_start_field:20s} → {end_field:20s} "
                f"from {p.source_record_id:8s}] = {p}"
            )
        print()


if __name__ == "__main__":
    demo_jane()