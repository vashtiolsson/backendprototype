"""
Transformation engine for the Occupation concept.

Reads:
  data/raw/*.csv              synthetic SSBTEK source data, at project root
  src/mappings/occupation.json declarative Occupation rules

Run from the project root:
  python -m src.transform.occupation
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from src.models.occupation import Occupation, OccupationType


PROJECT_ROOT  = Path(__file__).resolve().parent.parent.parent
DATA_DIR      = PROJECT_ROOT / "data" / "raw"
MAPPINGS_FILE = PROJECT_ROOT / "src" / "mappings" / "occupation.json"

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


def _safe_int(value: str | None) -> int | None:
    """Parse an optional integer value, such as scope_pct or study_pace_pct."""
    if value is None or value == "":
        return None

    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return None


# ── Core transformation ───────────────────────────────────────────────────────

def transform_occupation(
    personal_id: str,
    mappings: list[dict] | None = None,
    data_dir: Path = DATA_DIR,
) -> list[Occupation]:
    """
    Apply all Occupation-targeting mappings to one person's source data
    and return a list of Occupation instances.
    """
    if mappings is None:
        mappings = load_mappings()

    rules_by_file: dict[str, list[dict]] = defaultdict(list)
    for rule in mappings:
        rules_by_file[rule["source_file"]].append(rule)

    occupations: list[Occupation] = []

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
                    occupation_type = OccupationType(rule["target_value"])

                    source_field = rule["source_field"]
                    scope_field = rule.get("scope_field")
                    description_field = rule.get("description_field")

                    source_value = _safe_text(row.get(source_field))
                    source_description = (
                        _safe_text(row.get(description_field))
                        if description_field
                        else None
                    )
                    scope_pct = (
                        _safe_int(row.get(scope_field))
                        if scope_field
                        else None
                    )

                    if source_value is None:
                        continue

                    occupations.append(Occupation(
                        occupation_type=occupation_type,
                        source_value=source_value,
                        source_description=source_description,
                        scope_pct=scope_pct,
                        source_file=filename,
                        source_field=source_field,
                        source_record_id=f"row{row_idx}",
                    ))

    return occupations


# ── Demo: walk Jane's occupations end-to-end ──────────────────────────────────

def demo_jane() -> None:
    print("=" * 64)
    print(f"  Resolving Occupation concept for {JANE_PNR} (Jane Doe)")
    print("=" * 64)
    print()
    print(f"  Project root: {PROJECT_ROOT}")
    print(f"  Data dir:     {DATA_DIR}")
    print(f"  Mappings:     {MAPPINGS_FILE}")
    print()

    occupations = transform_occupation(JANE_PNR)

    if not occupations:
        print("  No occupations found. Did you run synthetic.py first?")
        print(f"  Expected CSVs in: {DATA_DIR}")
        return

    print(f"Found {len(occupations)} Occupation instance(s):\n")

    by_file: dict[str, list[Occupation]] = defaultdict(list)
    for occupation in occupations:
        by_file[occupation.source_file].append(occupation)

    for filename, items in by_file.items():
        print(f"  {filename}  ({len(items)} occupation(s))")
        for occupation in items:
            scope = (
                f"{occupation.scope_pct}%"
                if occupation.scope_pct is not None
                else "None"
            )

            description = (
                occupation.source_description
                if occupation.source_description is not None
                else "None"
            )

            print(
                f"    [{occupation.source_field:20s} "
                f"from {occupation.source_record_id:8s}] "
                f"= {occupation.occupation_type.value:10s} "
                f"source_value={occupation.source_value!r}, "
                f"scope={scope}, "
                f"description={description!r}"
            )
        print()


if __name__ == "__main__":
    demo_jane()