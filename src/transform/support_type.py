"""
Transformation engine for the SupportType concept.

Reads:
  data/raw/*.csv                  synthetic SSBTEK source data
  src/mappings/support_type.json  declarative SupportType mapping rules

Run from the project root:
  python -m src.transform.support_type
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from pydantic import ValidationError

from src.models.support_type import (
    SupportGroupValue,
    SupportType,
    SupportTypeValue,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = PROJECT_ROOT / "data" / "raw"
MAPPINGS_FILE = PROJECT_ROOT / "src" / "mappings" / "support_type.json"

JANE_PNR = "20000421-1234"


# Fallback ontology hierarchy.
# Ideally, target_group or target_group_map should come from the mapping file.
SUPPORT_GROUP_BY_TYPE = {
    "StudyGrant": "StudySupport",
    "StudyLoan": "StudySupport",
    "ActivitySupport": "WorkSupport",
}


RECORD_ID_FIELDS = [
    "record_id",
    "decision_id",
    "case_id",
    "payment_id",
    "period_id",
    "activity_id",
]


def load_mappings(path: Path = MAPPINGS_FILE) -> list[dict[str, Any]]:
    """Return the list of rules from the mapping specification file."""

    return json.loads(path.read_text(encoding="utf-8"))["rules"]


def _safe_text(value: Any) -> Optional[str]:
    """Normalize a source text value without changing its meaning."""

    if value is None:
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def _normalize_key(value: Any) -> Optional[str]:
    """
    Normalize source values so they can be matched against target_value_map.

    Example:
      GRUNDB -> grundb
      Activity Support -> activity support
    """

    value = _safe_text(value)

    if value is None:
        return None

    return value.lower()


def _normalize_value_map(value_map: dict[str, str]) -> dict[str, str]:
    """Normalize all mapping keys to lowercase."""

    return {
        str(source_key).strip().lower(): target_value
        for source_key, target_value in value_map.items()
    }


def _get_source_value_field(rule: dict[str, Any]) -> str:
    """
    Return the field containing the source value.

    Usually this is the same as source_field, but the mapping file may
    explicitly define source_value_field.
    """

    return rule.get("source_value_field") or rule["source_field"]


def _get_source_description_field(rule: dict[str, Any]) -> Optional[str]:
    """
    Return the optional source description field.

    Supports both the newer name source_description_field and the older
    name description_field for backwards compatibility.
    """

    return rule.get("source_description_field") or rule.get("description_field")


def _get_mapping_rule_id(rule: dict[str, Any]) -> str:
    """
    Return a stable mapping rule ID.

    The mapping file should ideally define an explicit id.
    The fallback exists so older mapping files still run.
    """

    if rule.get("id"):
        return rule["id"]

    source_file = rule["source_file"].replace(".csv", "")
    source_field = rule["source_field"]

    return f"support.{source_file}.{source_field}"


def _infer_source_record_id(row: dict[str, Any], row_idx: int) -> str:
    """
    Create a source record identifier.

    Prefer an existing source ID field if available.
    Otherwise fall back to the row number.
    """

    for field in RECORD_ID_FIELDS:
        value = _safe_text(row.get(field))
        if value is not None:
            return f"{field}:{value}"

    return f"row{row_idx}"


def _resolve_target_support_type(
    rule: dict[str, Any],
    source_key: str,
) -> Optional[str]:
    """
    Resolve the ontology-level support type.

    Supports:
      - target_value for rules where every row maps to the same value
      - target_value_map for rules where different source values map differently
    """

    if "target_value_map" in rule:
        target_value_map = _normalize_value_map(rule["target_value_map"])
        return target_value_map.get(source_key)

    if "target_value" in rule:
        return rule["target_value"]

    return None


def _resolve_target_support_group(
    rule: dict[str, Any],
    source_key: str,
    target_support_type: str,
) -> Optional[str]:
    """
    Resolve the broader ontology support group.

    Supports:
      - target_group for constant group mappings
      - target_group_map for source-value-specific group mappings
      - fallback inference from the target support type
    """

    if "target_group_map" in rule:
        target_group_map = _normalize_value_map(rule["target_group_map"])
        mapped_group = target_group_map.get(source_key)

        if mapped_group is not None:
            return mapped_group

    if "target_group" in rule:
        return rule["target_group"]

    return SUPPORT_GROUP_BY_TYPE.get(target_support_type)


def transform_support_type(
    personal_id: str = JANE_PNR,
    mappings: Optional[list[dict[str, Any]]] = None,
    data_dir: Optional[Path] = None,
) -> list[SupportType]:
    """
    Apply SupportType mapping rules to one person's source data.

    The transformer:
      1. reads relevant CSV rows,
      2. applies approved mapping rules,
      3. creates SupportType Pydantic objects,
      4. lets Pydantic validate the final result.
    """

    if data_dir is None:
        data_dir = DATA_DIR

    print("\n[TRANSFORMER] Starting SupportType transformation", flush=True)
    print(f"[TRANSFORMER] Person ID: {personal_id}", flush=True)
    print(f"[TRANSFORMER] Data directory: {data_dir}", flush=True)

    if mappings is None:
        print(
            f"[TRANSFORMER] No frontend mappings received. Loading mapping file: {MAPPINGS_FILE}",
            flush=True,
        )
        mappings = load_mappings()
    else:
        print("[TRANSFORMER] Using approved mappings from frontend/API", flush=True)

    print(f"[TRANSFORMER] Mapping rules received: {len(mappings)}", flush=True)

    rules_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for rule in mappings:
        if rule.get("target_class") != "SupportType":
            print(
                f"[TRANSFORMER] Skipping non-SupportType rule: {rule.get('id', 'missing-id')}",
                flush=True,
            )
            continue

        source_file = rule.get("source_file")

        if not source_file:
            print(
                f"[TRANSFORMER] Skipping rule without source_file: {rule}",
                flush=True,
            )
            continue

        rules_by_file[source_file].append(rule)

    print(
        f"[TRANSFORMER] Files with SupportType rules: {len(rules_by_file)}",
        flush=True,
    )

    support_types: list[SupportType] = []

    for filename, rules in rules_by_file.items():
        path = data_dir / filename

        print(f"[TRANSFORMER] Reading file: {filename}", flush=True)

        if not path.exists():
            print(f"[TRANSFORMER] ⚠ {filename} not found at {path} — skipping", flush=True)
            continue

        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            for row_idx, row in enumerate(reader):
                if row.get("personal_id") != personal_id:
                    continue

                print(
                    f"[TRANSFORMER] Found row for person in {filename}, row {row_idx}",
                    flush=True,
                )

                for rule in rules:
                    source_field = rule["source_field"]
                    source_value_field = _get_source_value_field(rule)
                    source_description_field = _get_source_description_field(rule)

                    source_value = _safe_text(row.get(source_value_field))
                    source_key = _normalize_key(source_value)

                    if source_value is None or source_key is None:
                        print(
                            f"[TRANSFORMER] Skipping empty source value in "
                            f"{filename}.{source_value_field}",
                            flush=True,
                        )
                        continue

                    target_support_type = _resolve_target_support_type(
                        rule=rule,
                        source_key=source_key,
                    )

                    if target_support_type is None:
                        print(
                            f"[TRANSFORMER] No target mapping for "
                            f"{filename}.{source_field}={source_value!r} — skipping",
                            flush=True,
                        )
                        continue

                    target_support_group = _resolve_target_support_group(
                        rule=rule,
                        source_key=source_key,
                        target_support_type=target_support_type,
                    )

                    if target_support_group is None:
                        print(
                            f"[TRANSFORMER] ⚠ No support group found for "
                            f"{filename}.{source_field}={source_value!r} — skipping",
                            flush=True,
                        )
                        continue

                    source_description = (
                        _safe_text(row.get(source_description_field))
                        if source_description_field
                        else None
                    )

                    try:
                        support_type = SupportType(
                            support_type=SupportTypeValue(target_support_type),
                            support_group=SupportGroupValue(target_support_group),
                            source_value=source_value,
                            source_description=source_description,
                            source_file=filename,
                            source_field=source_field,
                            source_record_id=_infer_source_record_id(row, row_idx),
                            mapping_rule_id=_get_mapping_rule_id(rule),
                            mapping_rationale=rule.get("rationale"),
                        )

                    except (ValueError, ValidationError) as error:
                        print(
                            f"[TRANSFORMER] ⚠ Invalid SupportType transformation skipped: "
                            f"{filename}.{source_field}={source_value!r}",
                            flush=True,
                        )
                        print(f"[TRANSFORMER] Reason: {error}", flush=True)
                        continue

                    support_types.append(support_type)

                    print(
                        f"[TRANSFORMER] Created SupportType: "
                        f"{source_value!r} -> {target_support_type}",
                        flush=True,
                    )

    print(
        f"[TRANSFORMER] Finished. Created {len(support_types)} SupportType object(s).",
        flush=True,
    )

    return support_types


def demo_jane() -> None:
    print("=" * 64)
    print(f"  Resolving SupportType concept for {JANE_PNR} (Jane Doe)")
    print("=" * 64)
    print()
    print(f"  Project root: {PROJECT_ROOT}")
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
                f"    [{support_type.source_field:24s} "
                f"from {support_type.source_record_id:18s}] "
                f"= {support_type.support_type.value:15s} "
                f"group={support_type.support_group.value:13s} "
                f"source_value={support_type.source_value!r}, "
                f"description={description!r}, "
                f"rule={support_type.mapping_rule_id}"
            )

        print()


if __name__ == "__main__":
    demo_jane()