"""
Transformer for the SupportType concept.

Takes the matcher's source-value records, resolves them to ontology values
using the rule's ``target_value`` / ``target_value_map`` and group fields,
and produces validated SupportType Pydantic objects.

Changes from the previous version
---------------------------------
- The reasoner's confidence and evidence are passed through to each
  transformed object's ``meta`` block, so the UI can show why a final result
  was produced.
- Successful transformations are persisted via the storage module.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import ValidationError

from src.new.matcher_st import DEFAULT_PERSON_ID, match_support_type
from src.new.model_st import (
    SupportGroupValue,
    SupportType,
    SupportTypeValue,
)


SUPPORT_GROUP_BY_TYPE = {
    "StudyGrant": "StudySupport",
    "StudyLoan": "StudySupport",
    "ActivitySupport": "WorkSupport",
}


def _normalize_value_map(value_map: dict[str, str]) -> dict[str, str]:
    return {
        str(k).strip().lower(): v
        for k, v in value_map.items()
    }


def _resolve_target_support_type(
    rule: dict[str, Any], source_key: str
) -> Optional[str]:
    if "target_value_map" in rule:
        return _normalize_value_map(rule["target_value_map"]).get(source_key)
    if "target_value" in rule:
        return rule["target_value"]
    return None


def _resolve_target_support_group(
    rule: dict[str, Any], source_key: str, target_support_type: str
) -> Optional[str]:
    if "target_group_map" in rule:
        mapped = _normalize_value_map(rule["target_group_map"]).get(source_key)
        if mapped is not None:
            return mapped
    if "target_group" in rule:
        return rule["target_group"]
    return SUPPORT_GROUP_BY_TYPE.get(target_support_type)


def _build_support_type_object(
    matched_record: dict[str, Any],
    target_support_type: str,
    target_support_group: str,
) -> SupportType:
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


def transform_support_type_matches(
    matcher_output: dict[str, Any],
    persist: bool = True,
) -> dict[str, Any]:
    """
    Convert matcher output into validated SupportType objects. If
    ``persist`` is True, the result is also written to disk by the storage
    module so the UI can show transformation history.
    """

    person_id = matcher_output.get("person_id", DEFAULT_PERSON_ID)

    print(f"\n[TRANSFORMER] Person: {person_id}", flush=True)

    matched_source_values = matcher_output.get("matched_source_values", [])

    transformed_objects: list[dict[str, Any]] = []
    unmatched_values: list[dict[str, Any]] = []

    for missing in matcher_output.get("missing_source_values", []):
        unmatched_values.append({**missing, "stage": "matcher"})

    for matched_record in matched_source_values:
        source_file = matched_record["source_file"]
        source_field = matched_record["source_field"]
        source_value = matched_record["source_value"]
        source_key = matched_record["normalized_source_value"]
        rule = matched_record.get("mapping_rule", {})
        reasoner = matched_record.get("reasoner") or {}

        target_support_type = _resolve_target_support_type(rule, source_key)
        if target_support_type is None:
            unmatched_values.append(
                _unmatched_record(
                    matched_record, person_id,
                    reason=(
                        "No approved target_value or target_value_map entry "
                        "found for this source value."
                    ),
                )
            )
            continue

        target_support_group = _resolve_target_support_group(
            rule, source_key, target_support_type
        )
        if target_support_group is None:
            unmatched_values.append(
                _unmatched_record(
                    matched_record, person_id,
                    reason="No support group could be resolved.",
                    extra={"target_support_type": target_support_type},
                )
            )
            continue

        try:
            obj = _build_support_type_object(
                matched_record=matched_record,
                target_support_type=target_support_type,
                target_support_group=target_support_group,
            )
        except (ValueError, ValidationError) as error:
            unmatched_values.append(
                _unmatched_record(
                    matched_record, person_id,
                    reason=f"Pydantic validation failed: {error}",
                    extra={
                        "target_support_type": target_support_type,
                        "target_support_group": target_support_group,
                    },
                )
            )
            continue

        payload = obj.model_dump(mode="json")
        # Attach reasoner-side evidence for the UI.
        payload["meta"] = {
            "reasoner_confidence": reasoner.get("confidence"),
            "reasoner_evidence": reasoner.get("evidence"),
            "csv_row_number": matched_record.get("csv_row_number"),
        }
        transformed_objects.append(payload)

    fallback_used = len(transformed_objects) == 0

    result = {
        "concept": "SupportType",
        "person_id": person_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "matches": transformed_objects,
        "unmatched_values": unmatched_values,
        "skipped_files": matcher_output.get("skipped_files", []),
        "files_with_no_person_rows": matcher_output.get("files_with_no_person_rows", []),
        "reasoner_fields_used": matcher_output.get("reasoner_fields_used", []),
        "fallback": {
            "concept": "SupportType",
            "fallback_used": fallback_used,
            "fallback_value": [],
            "reason": (
                "No SupportType objects could be transformed for this person."
                if fallback_used else None
            ),
        },
        "summary": {
            "matched_source_value_count": len(matched_source_values),
            "transformed_object_count": len(transformed_objects),
            "unmatched_count": len(unmatched_values),
            "skipped_file_count": len(matcher_output.get("skipped_files", [])),
        },
    }

    if persist:
        try:
            from src.new.storage_st import save_transformation
            transformation_id = save_transformation(result)
            result["transformation_id"] = transformation_id
            print(f"[TRANSFORMER] Saved transformation as {transformation_id}", flush=True)
        except Exception as exc:
            # Persistence failures shouldn't break the pipeline; surface them.
            result["persistence_error"] = str(exc)
            print(f"[TRANSFORMER] Persistence failed: {exc}", flush=True)

    print(
        f"[TRANSFORMER] Done. Created {len(transformed_objects)} object(s).",
        flush=True,
    )
    return result


def _unmatched_record(
    matched_record: dict[str, Any],
    person_id: str,
    reason: str,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    record = {
        "stage": "transformer",
        "concept": "SupportType",
        "person_id": person_id,
        "source_file": matched_record["source_file"],
        "source_field": matched_record["source_field"],
        "source_value": matched_record["source_value"],
        "normalized_source_value": matched_record.get("normalized_source_value"),
        "source_record_id": matched_record.get("source_record_id"),
        "mapping_rule_id": matched_record.get("mapping_rule_id"),
        "reason": reason,
        "fallback_used": True,
    }
    if extra:
        record.update(extra)
    return record


def run_support_type_pipeline(
    person_id: str = DEFAULT_PERSON_ID,
    persist: bool = True,
) -> dict[str, Any]:
    matcher_output = match_support_type(person_id=person_id)
    return transform_support_type_matches(matcher_output, persist=persist)


if __name__ == "__main__":
    result = run_support_type_pipeline()
    print()
    for item in result["matches"]:
        print(
            f"  {item['source_file']}.{item['source_field']} "
            f"{item['source_value']!r} -> "
            f"{item['support_group']} ({item['support_type']})"
        )
