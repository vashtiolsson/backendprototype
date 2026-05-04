"""
Transformation engine for the Status concept.

Reads:
  data/raw/*.csv          synthetic SSBTEK source data, at project root
  src/mappings/status.json declarative Status rules

Run from the project root:
  python -m src.transform.status
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from src.models.status import Status, StatusType


PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent
DATA_DIR      = PROJECT_ROOT / "data" / "raw"
MAPPINGS_FILE = PROJECT_ROOT / "src" / "mappings" / "status.json"

JANE_PNR = "20000421-1234"


# ── Loading ───────────────────────────────────────────────────────────────────

def load_mappings(path: Path = MAPPINGS_FILE) -> list[dict]:
    """Return the list of rules from the mapping spec file."""
    return json.loads(path.read_text(encoding="utf-8"))["rules"]


# ── Value parsing ─────────────────────────────────────────────────────────────

def _safe_text(value: str | None) -> str | None:
    """Normalize a source text value."""
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def _normalize_key(value: str | None) -> str | None:
    """Normalize source values so they can be matched against target_value_map."""
    value = _safe_text(value)

    if value is None:
        return None

    return value.lower()


# ── Core transformation ───────────────────────────────────────────────────────

def transform_status(
    personal_id: str,
    mappings: list[dict] | None = None,
    data_dir: Path = DATA_DIR,
) -> list[Status]:
    """
    Apply all Status-targeting mappings to one person's source data
    and return a list of Status instances.
    """
    if mappings is None:
        mappings = load_mappings()

    rules_by_file: dict[str, list[dict]] = defaultdict(list)
    for rule in mappings:
        rules_by_file[rule["source_file"]].append(rule)

    statuses: list[Status] = []

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
                    source_field = rule["source_field"]
                    description_field = rule.get("description_field")
                    target_value_map = rule.get("target_value_map", {})

                    source_value = _safe_text(row.get(source_field))
                    source_key = _normalize_key(source_value)

                    if source_value is None or source_key is None:
                        continue

                    target_value = target_value_map.get(source_key)

                    if target_value is None:
                        continue

                    source_description = (
                        _safe_text(row.get(description_field))
                        if description_field
                        else None
                    )

                    statuses.append(Status(
                        status_type=StatusType(target_value),
                        source_value=source_value,
                        source_description=source_description,
                        source_file=filename,
                        source_field=source_field,
                        source_record_id=f"row{row_idx}",
                    ))

    return statuses


# ── Demo: walk Jane's statuses end-to-end ─────────────────────────────────────

def demo_jane() -> None:
    print("=" * 64)
    print(f"  Resolving Status concept for {JANE_PNR} (Jane Doe)")
    print("=" * 64)
    print()
    print(f"  Project root: {PROJECT_ROOT}")
    print(f"  Data dir:     {DATA_DIR}")
    print(f"  Mappings:     {MAPPINGS_FILE}")
    print()

    statuses = transform_status(JANE_PNR)

    if not statuses:
        print("  No statuses found. Did you run synthetic.py first?")
        print(f"  Expected CSVs in: {DATA_DIR}")
        return

    print(f"Found {len(statuses)} Status instance(s):\n")

    by_file: dict[str, list[Status]] = defaultdict(list)
    for status in statuses:
        by_file[status.source_file].append(status)

    for filename, items in by_file.items():
        print(f"  {filename}  ({len(items)} status(es))")
        for status in items:
            description = (
                status.source_description
                if status.source_description is not None
                else "None"
            )

            print(
                f"    [{status.source_field:20s} "
                f"from {status.source_record_id:8s}] "
                f"= {status.status_type.value:10s} "
                f"source_value={status.source_value!r}, "
                f"description={description!r}"
            )
        print()


if __name__ == "__main__":
    demo_jane()