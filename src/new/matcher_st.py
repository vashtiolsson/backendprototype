"""
Matcher for the SupportType concept.

Purpose:
  The reasoner identifies high-confidence CSV fields that appear relevant
  to the SupportType concept.

  The matcher then:
    1. takes only high-confidence reasoner fields,
    2. finds approved mapping rules for those fields,
    3. reads the matching person rows from the CSV files,
    4. extracts raw source values such as GRUNDB, GRUNDL, FK:AS,
    5. returns matched source records with provenance and mapping-rule context.

Important:
  The matcher does NOT create SupportType Pydantic objects.
  The matcher does NOT resolve GRUNDB -> StudyGrant.
  That is the transformer's job.

Run from project root:
  python3 -m src.new.matcher_st
"""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from src.new.reasoner_st import run_support_type_reasoner


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DATA_DIR = PROJECT_ROOT / "data" / "raw"
MAPPINGS_FILE = PROJECT_ROOT / "src" / "mappings" / "support_type.json"

DEFAULT_PERSON_ID = "20000421-1234"
DEFAULT_MIN_CONFIDENCE = 0.60

PERSON_ID_FIELDS = ("personal_id", "person_id", "pnr")

RECORD_ID_FIELDS = [
    "record_id",
    "decision_id",
    "case_id",
    "payment_id",
    "period_id",
    "activity_id",
]


# ---------------------------------------------------------------------------
# Loading and normalization helpers
# ---------------------------------------------------------------------------

def load_mappings(path: Path = MAPPINGS_FILE) -> list[dict[str, Any]]:
    """Load approved SupportType mapping rules."""

    return json.loads(path.read_text(encoding="utf-8"))["rules"]


def _safe_text(value: Any) -> Optional[str]:
    """Return a stripped text value, or None if the value is missing/empty."""

    if value is None:
        return None

    text = str(value).strip()

    if text == "":
        return None

    return text


def _normalize_key(value: Any) -> Optional[str]:
    """
    Normalize source values for later lookup in target_value_map.

    Examples:
      GRUNDB -> grundb
      FK:AS  -> fk:as
      Study grant -> study grant
    """

    text = _safe_text(value)

    if text is None:
        return None

    return text.lower()


def _get_source_value_field(rule: dict[str, Any]) -> str:
    """
    Return the source field that contains the raw value.

    Usually this is the same as source_field.
    A rule may explicitly define source_value_field when needed.
    """

    return rule.get("source_value_field") or rule["source_field"]


def _get_source_description_field(rule: dict[str, Any]) -> Optional[str]:
    """
    Return optional human-readable description field from the mapping rule.
    """

    return rule.get("source_description_field") or rule.get("description_field")


def _get_mapping_rule_id(rule: dict[str, Any]) -> str:
    """Return a stable mapping rule ID."""

    if rule.get("id"):
        return rule["id"]

    source_file = rule["source_file"].replace(".csv", "")
    source_field = rule["source_field"]

    return f"support.{source_file}.{source_field}"


def _infer_source_record_id(row: dict[str, Any], row_idx: int) -> str:
    """
    Create a stable source record identifier.

    Prefer an existing source record ID field.
    Fall back to row index when no source ID field exists.
    """

    for field in RECORD_ID_FIELDS:
        value = _safe_text(row.get(field))
        if value is not None:
            return f"{field}:{value}"

    return f"row{row_idx}"


def _row_belongs_to_person(row: dict[str, Any], person_id: str) -> bool:
    """Check whether a source row belongs to the requested person."""

    return any(row.get(field) == person_id for field in PERSON_ID_FIELDS)


# ---------------------------------------------------------------------------
# Reasoner field filtering
# ---------------------------------------------------------------------------

def _accepted_reasoner_fields(
    reasoner_output: dict[str, Any],
    min_confidence: float,
) -> dict[tuple[str, str], dict[str, Any]]:
    """
    Convert high-confidence reasoner fields into a lookup.

    Key:
      (source_file, source_field)

    Value:
      reasoner field metadata
    """

    accepted: dict[tuple[str, str], dict[str, Any]] = {}

    for field in reasoner_output.get("fields", []):
        source_file = field.get("file") or field.get("source_file")
        source_field = field.get("name") or field.get("source_field")
        confidence = float(field.get("confidence", 0.0))

        if not source_file or not source_field:
            continue

        if confidence < min_confidence:
            continue

        if field.get("concept") not in [None, "SupportType"]:
            continue

        accepted[(source_file, source_field)] = field

    return accepted


def _rules_allowed_by_reasoner(
    mappings: list[dict[str, Any]],
    accepted_fields: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Keep only approved mapping rules that also have a high-confidence
    reasoner field.

    This is the core connection:

      reasoner accepted field
          +
      approved mapping rule
          =
      field may be matched
    """

    rules_by_file: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for rule in mappings:
        if rule.get("target_class") != "SupportType":
            continue

        source_file = rule.get("source_file")
        source_field = rule.get("source_field")

        if not source_file or not source_field:
            continue

        reasoner_key = (source_file, source_field)

        if reasoner_key not in accepted_fields:
            continue

        rule_with_reasoner = dict(rule)
        rule_with_reasoner["_reasoner"] = accepted_fields[reasoner_key]

        rules_by_file[source_file].append(rule_with_reasoner)

    return rules_by_file


def _public_mapping_rule(rule: dict[str, Any]) -> dict[str, Any]:
    """
    Return mapping rule without internal matcher-only metadata.

    The transformer still needs target_value, target_value_map,
    target_group, target_group_map, and rationale.
    """

    return {
        key: value
        for key, value in rule.items()
        if not key.startswith("_")
    }


# ---------------------------------------------------------------------------
# Main matcher
# ---------------------------------------------------------------------------

def match_support_type(
    person_id: str = DEFAULT_PERSON_ID,
    data_dir: Optional[Path] = None,
    mappings: Optional[list[dict[str, Any]]] = None,
    reasoner_output: Optional[dict[str, Any]] = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> dict[str, Any]:
    """
    Match high-confidence SupportType source fields to source values.

    Input:
      - person_id
      - CSV files
      - approved mapping rules
      - reasoner output

    Output:
      - matched source values
      - missing source values
      - skipped files
      - reasoner fields used

    The output is intentionally not a SupportType object yet.
    The transformer creates the final Pydantic objects.
    """

    if data_dir is None:
        data_dir = DATA_DIR

    if mappings is None:
        mappings = load_mappings()

    if reasoner_output is None:
        reasoner_output = run_support_type_reasoner(
            person_id=person_id,
            data_dir=data_dir,
        )

    print("\n[MATCHER] Starting SupportType matcher", flush=True)
    print(f"[MATCHER] Person ID: {person_id}", flush=True)
    print(f"[MATCHER] Data directory: {data_dir}", flush=True)
    print(f"[MATCHER] Minimum reasoner confidence: {min_confidence}", flush=True)

    accepted_fields = _accepted_reasoner_fields(
        reasoner_output=reasoner_output,
        min_confidence=min_confidence,
    )

    print(f"[MATCHER] High-confidence reasoner fields: {len(accepted_fields)}", flush=True)

    rules_by_file = _rules_allowed_by_reasoner(
        mappings=mappings,
        accepted_fields=accepted_fields,
    )

    print(f"[MATCHER] Files with usable mapping rules: {len(rules_by_file)}", flush=True)

    matched_source_values: list[dict[str, Any]] = []
    missing_source_values: list[dict[str, Any]] = []
    skipped_files: list[dict[str, Any]] = []

    for filename, rules in rules_by_file.items():
        path = data_dir / filename

        print(f"[MATCHER] Reading file: {filename}", flush=True)

        if not path.exists():
            skipped_files.append(
                {
                    "source_file": filename,
                    "reason": f"File not found at {path}",
                }
            )
            print(f"[MATCHER] File not found: {path}", flush=True)
            continue

        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)

            for row_idx, row in enumerate(reader):
                if not _row_belongs_to_person(row, person_id):
                    continue

                for rule in rules:
                    source_field = rule["source_field"]
                    source_value_field = _get_source_value_field(rule)
                    source_description_field = _get_source_description_field(rule)

                    source_value = _safe_text(row.get(source_value_field))
                    normalized_source_value = _normalize_key(source_value)

                    source_description = (
                        _safe_text(row.get(source_description_field))
                        if source_description_field
                        else None
                    )

                    source_record_id = _infer_source_record_id(row, row_idx)
                    mapping_rule_id = _get_mapping_rule_id(rule)

                    if source_value is None or normalized_source_value is None:
                        missing_source_values.append(
                            {
                                "concept": "SupportType",
                                "person_id": person_id,
                                "source_file": filename,
                                "source_field": source_field,
                                "source_value_field": source_value_field,
                                "source_value": None,
                                "source_record_id": source_record_id,
                                "mapping_rule_id": mapping_rule_id,
                                "reason": "Source value is missing or empty.",
                                "fallback_used": True,
                            }
                        )
                        continue

                    matched_record = {
                        "concept": "SupportType",
                        "person_id": person_id,
                        "source_file": filename,
                        "source_field": source_field,
                        "source_value_field": source_value_field,
                        "source_value": source_value,
                        "normalized_source_value": normalized_source_value,
                        "source_description_field": source_description_field,
                        "source_description": source_description,
                        "source_record_id": source_record_id,
                        "row_index": row_idx,
                        "mapping_rule_id": mapping_rule_id,
                        "mapping_rationale": rule.get("rationale"),
                        "reasoner": rule.get("_reasoner"),
                        "mapping_rule": _public_mapping_rule(rule),
                    }

                    matched_source_values.append(matched_record)

                    print(
                        f"[MATCHER] Matched source value "
                        f"{filename}.{source_field}={source_value!r} "
                        f"using rule {mapping_rule_id}",
                        flush=True,
                    )

    fallback_used = len(matched_source_values) == 0

    result = {
        "concept": "SupportType",
        "person_id": person_id,
        "min_confidence": min_confidence,
        "reasoner_fields_used": list(accepted_fields.values()),
        "matched_source_values": matched_source_values,
        "missing_source_values": missing_source_values,
        "skipped_files": skipped_files,
        "fallback": {
            "concept": "SupportType",
            "fallback_used": fallback_used,
            "fallback_value": [],
            "reason": (
                "No SupportType source values could be matched for this person."
                if fallback_used
                else None
            ),
        },
        "summary": {
            "matched_source_value_count": len(matched_source_values),
            "missing_source_value_count": len(missing_source_values),
            "high_confidence_field_count": len(accepted_fields),
            "usable_mapping_file_count": len(rules_by_file),
        },
    }

    print(
        f"[MATCHER] Finished. Prepared "
        f"{len(matched_source_values)} source value(s) for transformation.",
        flush=True,
    )

    return result


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_jane() -> None:
    """Run only the matcher for the thesis demo person."""

    result = match_support_type(DEFAULT_PERSON_ID)

    print()
    print("=" * 72)
    print(f"SupportType matcher result for {DEFAULT_PERSON_ID}")
    print("=" * 72)
    print()

    matches = result["matched_source_values"]

    if not matches:
        print("No SupportType source values found.")
        print(f"Fallback used: {result['fallback']['fallback_used']}")
        print(f"Reason: {result['fallback']['reason']}")
        return

    for item in matches:
        print(
            f"{item['source_file']}.{item['source_field']} "
            f"{item['source_value']!r}"
        )
        print(f"  normalized value: {item['normalized_source_value']}")
        print(f"  source_record_id: {item['source_record_id']}")
        print(f"  mapping_rule_id:  {item['mapping_rule_id']}")

        reasoner = item.get("reasoner") or {}
        if reasoner.get("confidence") is not None:
            print(f"  reasoner confidence: {reasoner.get('confidence')}")

        if item.get("mapping_rationale"):
            print(f"  rationale: {item['mapping_rationale']}")

        print()

    if result["missing_source_values"]:
        print("Missing source values:")
        for item in result["missing_source_values"]:
            print(
                f"  - {item.get('source_file')}.{item.get('source_field')}: "
                f"{item.get('reason')}"
            )


if __name__ == "__main__":
    demo_jane()