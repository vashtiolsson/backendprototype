"""
Transformation engine for the SupportType concept.

Reads:
  data/raw/*.csv                 synthetic SSBTEK source data, at project root
  src/mappings/support_type.json declarative SupportType rules

Run from the project root:
  python -m src.transform.support_type
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from src.models.support_type import SupportType, SupportTypeValue


BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = BACKEND_ROOT / "mapping_copilot" / "data" / "raw"
MAPPINGS_FILE = BACKEND_ROOT / "src" / "mappings" / "support_type.json"

JANE_PNR = "20000421-1234"


def load_mappings(path: Path = MAPPINGS_FILE) -> list[dict]:
    """Return the list of rules from the mapping spec file."""
    return json.loads(path.read_text(encoding="utf-8"))["rules"]


def _safe_text(value: str | None) -> str | None:
    """Normalize a source text value."""
    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def _normalize_key(value: str | None) -> str | None:
    """
    Normalize source values so they can be matched against target_value_map.

    This transformer uses lowercase matching so JSON mappings can contain
    either uppercase source codes like GRUNDB or lowercase values like
    student_grant.
    """
    value = _safe_text(value)

    if value is None:
        return None

    return value.lower()


def _normalize_target_value_map(target_value_map: dict[str, str]) -> dict[str, str]:
    """
    Normalize all mapping keys to lowercase.

    This fixes cases where the JSON contains keys such as:
      "GRUNDB": "StudyGrant"
      "GRUNDL": "StudyLoan"

    while _normalize_key(source_value) produces:
      "grundb"
      "grundl"
    """
    return {
        str(source_key).strip().lower(): target_value
        for source_key, target_value in target_value_map.items()
    }


def transform_support_type(
    personal_id: str,
    mappings: list[dict] | None = None,
    data_dir: Path = DATA_DIR,
) -> list[SupportType]:
    """
    Apply all SupportType-targeting mappings to one person's source data
    and return a list of SupportType instances.
    """
    if mappings is None:
        mappings = load_mappings()

    rules_by_file: dict[str, list[dict]] = defaultdict(list)
    for rule in mappings:
        rules_by_file[rule["source_file"]].append(rule)

    support_types: list[SupportType] = []

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

                    source_value = _safe_text(row.get(source_field))
                    source_key = _normalize_key(source_value)

                    if source_value is None or source_key is None:
                        continue

                    target_value_map = _normalize_target_value_map(
                        rule.get("target_value_map", {})
                    )

                    target_value = target_value_map.get(source_key)

                    if target_value is None:
                        continue

                    source_description = (
                        _safe_text(row.get(description_field))
                        if description_field
                        else None
                    )

                    support_types.append(SupportType(
                        support_type=SupportTypeValue(target_value),
                        source_value=source_value,
                        source_description=source_description,
                        source_file=filename,
                        source_field=source_field,
                        source_record_id=f"row{row_idx}",
                    ))

    return support_types


def demo_jane() -> None:
    print("=" * 64)
    print(f"  Resolving SupportType concept for {JANE_PNR} (Jane Doe)")
    print("=" * 64)
    print()
    print(f"  Project root: {BACKEND_ROOT}")
    print(f"  Data dir:     {DATA_DIR}")
    print(f"  Mappings:     {MAPPINGS_FILE}")
    print()

    support_types = transform_support_type(JANE_PNR)

    if not support_types:
        print("  No support types found. Did you run synthetic.py first?")
        print(f"  Expected CSVs in: {DATA_DIR}")
        return

    print(f"Found {len(support_types)} SupportType instance(s):\n")

    by_file: dict[str, list[SupportType]] = defaultdict(list)
    for support_type in support_types:
        by_file[support_type.source_file].append(support_type)

    for filename, items in by_file.items():
        print(f"  {filename}  ({len(items)} support type(s))")
        for support_type in items:
            description = (
                support_type.source_description
                if support_type.source_description is not None
                else "None"
            )

            print(
                f"    [{support_type.source_field:20s} "
                f"from {support_type.source_record_id:8s}] "
                f"= {support_type.support_type.value:15s} "
                f"source_value={support_type.source_value!r}, "
                f"description={description!r}"
            )
        print()


if __name__ == "__main__":
    demo_jane()