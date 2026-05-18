"""
Rule-authoring API.

Use this module to create new approved mapping rules at runtime, either
from scratch or by promoting a previously-unmatched source value into a
rule.

Authored rules are stored in src/storage/user_rules/ and are picked up
automatically by the matcher on the next run via storage.load_all_rules().
They never modify src/mappings/*.json -- those remain the curated system
rules and changes there should go through code review like any other.

Authoring shapes
----------------
1. Constant-value rule (every covered row maps to the same target):

       propose_constant_value_rule(
           source_file="af_benefit_type_decision.csv",
           source_field="benefit_type",
           target_value="ActivitySupport",
           author="vashti",
           rationale="AF activity-support benefit rows map to ActivitySupport.",
       )

2. Value-map rule (different source values map to different targets):

       propose_value_map_rule(
           source_file="csn_approved_amounts.csv",
           source_field="amount_type_code",
           target_value_map={"GRUNDB": "StudyGrant", "GRUNDL": "StudyLoan"},
           author="vashti",
           rationale="...",
       )

3. From an unmatched match record (the common UI path):

       propose_rule_from_match(
           unmatched_record,
           target_value="StudyGrant",
           author="vashti",
           rationale="Newly observed code; analyst confirmed it is a grant.",
       )

All three end up writing to the same user_rules store with the same
envelope.
"""

from __future__ import annotations

from typing import Any, Optional

from src.new.model_st import SupportGroupValue, SupportTypeValue
from src.new.storage_st import save_user_rule


ALLOWED_SUPPORT_TYPES = {item.value for item in SupportTypeValue}
ALLOWED_SUPPORT_GROUPS = {item.value for item in SupportGroupValue}


def _validate_target_values(values: list[str]) -> None:
    bad = [v for v in values if v not in ALLOWED_SUPPORT_TYPES]
    if bad:
        raise ValueError(
            f"Unknown SupportType target value(s): {bad}. "
            f"Allowed: {sorted(ALLOWED_SUPPORT_TYPES)}"
        )


def _validate_target_groups(values: list[str]) -> None:
    bad = [v for v in values if v not in ALLOWED_SUPPORT_GROUPS]
    if bad:
        raise ValueError(
            f"Unknown SupportGroup target value(s): {bad}. "
            f"Allowed: {sorted(ALLOWED_SUPPORT_GROUPS)}"
        )


def propose_constant_value_rule(
    source_file: str,
    source_field: str,
    target_value: str,
    author: str,
    rationale: Optional[str] = None,
    description_field: Optional[str] = None,
    source_value_field: Optional[str] = None,
    target_group: Optional[str] = None,
) -> str:
    """Author a rule where every covered row maps to a single target value."""

    _validate_target_values([target_value])
    if target_group is not None:
        _validate_target_groups([target_group])

    rule: dict[str, Any] = {
        "source_file": source_file,
        "source_field": source_field,
        "source_value_field": source_value_field or source_field,
        "target_class": "SupportType",
        "target_property": "supportType",
        "target_value": target_value,
        "transformation": f"{source_field}_to_support_type",
    }
    if description_field:
        rule["description_field"] = description_field
    if target_group is not None:
        rule["target_group"] = target_group

    return save_user_rule(rule=rule, author=author, rationale=rationale)


def propose_value_map_rule(
    source_file: str,
    source_field: str,
    target_value_map: dict[str, str],
    author: str,
    rationale: Optional[str] = None,
    description_field: Optional[str] = None,
    source_value_field: Optional[str] = None,
    target_group_map: Optional[dict[str, str]] = None,
) -> str:
    """Author a rule where source values map differently to target values."""

    if not target_value_map:
        raise ValueError("target_value_map must contain at least one entry")
    _validate_target_values(list(target_value_map.values()))
    if target_group_map:
        _validate_target_groups(list(target_group_map.values()))

    rule: dict[str, Any] = {
        "source_file": source_file,
        "source_field": source_field,
        "source_value_field": source_value_field or source_field,
        "target_class": "SupportType",
        "target_property": "supportType",
        "target_value_map": target_value_map,
        "transformation": f"{source_field}_value_map_to_support_type",
    }
    if description_field:
        rule["description_field"] = description_field
    if target_group_map:
        rule["target_group_map"] = target_group_map

    return save_user_rule(rule=rule, author=author, rationale=rationale)


def propose_rule_from_match(
    match_record: dict[str, Any],
    target_value: str,
    author: str,
    rationale: Optional[str] = None,
    target_group: Optional[str] = None,
    mode: str = "auto",
) -> str:
    """
    Convert a matched-but-unmapped source value into a new approved rule.

    ``mode`` selects the rule shape:
        - "value_map" : encode just this source value as a map entry, so
                        only this value (not others) is covered.
        - "constant"  : every row in this field/file maps to ``target_value``.
        - "auto"      : pick value_map if a source_value is present,
                        constant otherwise.
    """

    source_file = match_record.get("source_file")
    source_field = match_record.get("source_field")
    source_value = match_record.get("source_value")
    source_value_field = (
        match_record.get("source_value_field") or source_field
    )
    description_field = match_record.get("source_description_field")

    if not source_file or not source_field:
        raise ValueError(
            "match_record must include source_file and source_field"
        )

    if mode == "auto":
        mode = "value_map" if source_value else "constant"

    if mode == "value_map":
        if not source_value:
            raise ValueError(
                "Cannot build a value_map rule without a source_value"
            )
        return propose_value_map_rule(
            source_file=source_file,
            source_field=source_field,
            target_value_map={source_value: target_value},
            author=author,
            rationale=rationale,
            description_field=description_field,
            source_value_field=source_value_field,
            target_group_map=(
                {source_value: target_group} if target_group else None
            ),
        )

    if mode == "constant":
        return propose_constant_value_rule(
            source_file=source_file,
            source_field=source_field,
            target_value=target_value,
            author=author,
            rationale=rationale,
            description_field=description_field,
            source_value_field=source_value_field,
            target_group=target_group,
        )

    raise ValueError(f"Unknown mode: {mode}")


if __name__ == "__main__":
    # Tiny smoke run; safe to delete the produced file after inspection.
    rule_id = propose_constant_value_rule(
        source_file="af_benefit_type_decision.csv",
        source_field="benefit_type",
        target_value="ActivitySupport",
        author="vashti",
        rationale="Demo run of rule authoring.",
    )
    print(f"Wrote rule {rule_id}")
