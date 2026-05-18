"""
Transformer for the SupportType concept.

Purpose:
  The matcher finds source values that are relevant for SupportType.

  The transformer then:
    1. receives matched source values from the matcher,
    2. resolves raw source values using approved mapping rules,
    3. maps values such as GRUNDB, GRUNDL, FK:AS to ontology values,
    4. resolves the broader support group,
    5. creates validated SupportType Pydantic objects,
    6. returns transformed objects with provenance and fallback information.

Example:
  matcher output:
    source_value = GRUNDB
    mapping rule contains:
      GRUNDB -> StudyGrant
      StudyGrant -> StudySupport

  transformer output:
    SupportType(
      support_type="StudyGrant",
      support_group="StudySupport",
      source_value="GRUNDB",
      source_file="csn_approved_amounts.csv",
      source_field="amount_type_code",
      ...
    )

Run from project root:
  python3 -m src.new.transformer_st
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import ValidationError

from src.new.matcher_st import DEFAULT_PERSON_ID, match_support_type
from src.new.model_st import (
    SupportGroupValue,
    SupportType,
    SupportTypeValue,
)


# Fallback ontology hierarchy.
# This is used if the mapping rule gives a concrete support_type
# but does not explicitly provide support_group or target_group_map.
SUPPORT_GROUP_BY_TYPE = {
    "StudyGrant": "StudySupport",
    "StudyLoan": "StudySupport",
    "ActivitySupport": "WorkSupport",
}


# ---------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------

def _normalize_value_map(value_map: dict[str, str]) -> dict[str, str]:
    """Normalize mapping keys so lookups are case-insensitive."""

    return {
        str(source_key).strip().lower(): target_value
        for source_key, target_value in value_map.items()
    }


def _resolve_target_support_type(
    rule: dict[str, Any],
    source_key: str,
) -> Optional[str]:
    """
    Resolve the ontology-level support type from the approved mapping rule.

    Supports:
      - target_value:
          every row covered by the rule maps to the same target value

      - target_value_map:
          different source values map to different target values

    Example:
      source_key = "grundb"
      target_value_map["grundb"] = "StudyGrant"
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
    Resolve the broader SupportType group.

    Supports:
      - target_group:
          constant group for all rows covered by the rule

      - target_group_map:
          source-value-specific group

      - SUPPORT_GROUP_BY_TYPE:
          fallback from concrete support type
    """

    if "target_group_map" in rule:
        target_group_map = _normalize_value_map(rule["target_group_map"])
        mapped_group = target_group_map.get(source_key)

        if mapped_group is not None:
            return mapped_group

    if "target_group" in rule:
        return rule["target_group"]

    return SUPPORT_GROUP_BY_TYPE.get(target_support_type)


def _build_support_type_object(
    matched_record: dict[str, Any],
    target_support_type: str,
    target_support_group: str,
) -> SupportType:
    """Create and validate one SupportType Pydantic object."""

    return SupportType(
        support_type=SupportTypeValue(target_support_type),
        support_group=SupportGroupValue(target_support_group),
        source_value=matched_record["source_value"],
        source_description=matched_record.get("source_description"),
        source_file=matched_record["source_file"],
        source_field=matched_record["source_field"],
        source_record_id=matched_record["source_record_id"],
        mapping_rule_id=matched_record["mapping_rule_id"],
        mapping_rationale=matched_record.get("mapping_rationale"),
    )


# ---------------------------------------------------------------------------
# Main transformer
# ---------------------------------------------------------------------------

def transform_support_type_matches(
    matcher_output: dict[str, Any],
) -> dict[str, Any]:
    """
    Transform matched SupportType source records into validated Pydantic objects.

    Input:
      matcher output from match_support_type(...)

    Output:
      validated SupportType objects,
      unmatched values,
      fallback information,
      and summary.
    """

    person_id = matcher_output.get("person_id", DEFAULT_PERSON_ID)

    print("\n[TRANSFORMER] Starting SupportType transformer", flush=True)
    print(f"[TRANSFORMER] Person ID: {person_id}", flush=True)

    matched_source_values = matcher_output.get("matched_source_values", [])

    transformed_objects: list[SupportType] = []
    unmatched_values: list[dict[str, Any]] = []

    # Keep missing source values from the matcher in the final transformer result.
    for missing in matcher_output.get("missing_source_values", []):
        unmatched_values.append(
            {
                **missing,
                "stage": "matcher",
            }
        )

    for matched_record in matched_source_values:
        source_file = matched_record["source_file"]
        source_field = matched_record["source_field"]
        source_value = matched_record["source_value"]
        source_key = matched_record["normalized_source_value"]
        rule = matched_record.get("mapping_rule", {})

        target_support_type = _resolve_target_support_type(
            rule=rule,
            source_key=source_key,
        )

        if target_support_type is None:
            unmatched_values.append(
                {
                    "stage": "transformer",
                    "concept": "SupportType",
                    "person_id": person_id,
                    "source_file": source_file,
                    "source_field": source_field,
                    "source_value": source_value,
                    "normalized_source_value": source_key,
                    "source_record_id": matched_record.get("source_record_id"),
                    "mapping_rule_id": matched_record.get("mapping_rule_id"),
                    "reason": (
                        "No approved target_value or target_value_map entry "
                        "found for this source value."
                    ),
                    "fallback_used": True,
                }
            )

            print(
                f"[TRANSFORMER] No approved target support type for "
                f"{source_file}.{source_field}={source_value!r}",
                flush=True,
            )
            continue

        target_support_group = _resolve_target_support_group(
            rule=rule,
            source_key=source_key,
            target_support_type=target_support_type,
        )

        if target_support_group is None:
            unmatched_values.append(
                {
                    "stage": "transformer",
                    "concept": "SupportType",
                    "person_id": person_id,
                    "source_file": source_file,
                    "source_field": source_field,
                    "source_value": source_value,
                    "normalized_source_value": source_key,
                    "target_support_type": target_support_type,
                    "source_record_id": matched_record.get("source_record_id"),
                    "mapping_rule_id": matched_record.get("mapping_rule_id"),
                    "reason": "No support group could be resolved.",
                    "fallback_used": True,
                }
            )

            print(
                f"[TRANSFORMER] No support group for "
                f"{source_file}.{source_field}={source_value!r}",
                flush=True,
            )
            continue

        try:
            support_type = _build_support_type_object(
                matched_record=matched_record,
                target_support_type=target_support_type,
                target_support_group=target_support_group,
            )

        except (ValueError, ValidationError) as error:
            unmatched_values.append(
                {
                    "stage": "transformer",
                    "concept": "SupportType",
                    "person_id": person_id,
                    "source_file": source_file,
                    "source_field": source_field,
                    "source_value": source_value,
                    "normalized_source_value": source_key,
                    "target_support_type": target_support_type,
                    "target_support_group": target_support_group,
                    "source_record_id": matched_record.get("source_record_id"),
                    "mapping_rule_id": matched_record.get("mapping_rule_id"),
                    "reason": f"Pydantic validation failed: {error}",
                    "fallback_used": True,
                }
            )

            print(
                f"[TRANSFORMER] Pydantic validation failed for "
                f"{source_file}.{source_field}={source_value!r}: {error}",
                flush=True,
            )
            continue

        transformed_objects.append(support_type)

        print(
            f"[TRANSFORMER] Created SupportType object from "
            f"{source_file}.{source_field}={source_value!r} -> "
            f"{support_type.support_group.value} "
            f"({support_type.support_type.value})",
            flush=True,
        )

    fallback_used = len(transformed_objects) == 0

    result = {
        "concept": "SupportType",
        "person_id": person_id,
        "matches": [item.model_dump(mode="json") for item in transformed_objects],
        "unmatched_values": unmatched_values,
        "skipped_files": matcher_output.get("skipped_files", []),
        "reasoner_fields_used": matcher_output.get("reasoner_fields_used", []),
        "fallback": {
            "concept": "SupportType",
            "fallback_used": fallback_used,
            "fallback_value": [],
            "reason": (
                "No SupportType objects could be transformed for this person."
                if fallback_used
                else None
            ),
        },
        "summary": {
            "matched_source_value_count": len(matched_source_values),
            "transformed_object_count": len(transformed_objects),
            "unmatched_count": len(unmatched_values),
            "skipped_file_count": len(matcher_output.get("skipped_files", [])),
        },
    }

    print(
        f"[TRANSFORMER] Finished. Created "
        f"{len(transformed_objects)} SupportType object(s).",
        flush=True,
    )

    return result


def run_support_type_pipeline(
    person_id: str = DEFAULT_PERSON_ID,
) -> dict[str, Any]:
    """
    Run matcher + transformer together.

    This is the clean full SupportType pipeline:
      matcher finds source values
      transformer creates validated SupportType objects
    """

    matcher_output = match_support_type(person_id=person_id)

    return transform_support_type_matches(matcher_output)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_jane() -> None:
    """Run matcher + transformer for the thesis demo person."""

    result = run_support_type_pipeline(DEFAULT_PERSON_ID)

    print()
    print("=" * 72)
    print(f"SupportType transformer result for {DEFAULT_PERSON_ID}")
    print("=" * 72)
    print()

    matches = result["matches"]

    if not matches:
        print("No SupportType objects created.")
        print(f"Fallback used: {result['fallback']['fallback_used']}")
        print(f"Reason: {result['fallback']['reason']}")
        return

    for item in matches:
        print(
            f"{item['source_file']}.{item['source_field']} "
            f"{item['source_value']!r} -> "
            f"{item['support_group']} ({item['support_type']})"
        )
        print(f"  source_record_id: {item['source_record_id']}")
        print(f"  mapping_rule_id:  {item['mapping_rule_id']}")

        if item.get("mapping_rationale"):
            print(f"  rationale:        {item['mapping_rationale']}")

        print()

    if result["unmatched_values"]:
        print("Unmatched/fallback values:")
        for item in result["unmatched_values"]:
            print(
                f"  - {item.get('source_file')}.{item.get('source_field')} "
                f"{item.get('source_value')!r}: {item.get('reason')}"
            )


if __name__ == "__main__":
    demo_jane()