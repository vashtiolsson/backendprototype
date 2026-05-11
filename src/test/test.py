from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.models.support_type import SupportGroupValue, SupportTypeValue
from src.transform.support_type import MAPPINGS_FILE, transform_support_type

# Change this import if your reasoner file is saved somewhere else.
# Example alternatives could be:
# from src.reasoners.support_type import run_support_type_reasoner_on_all_csvs
# from src.reasoning.support_type import run_support_type_reasoner_on_all_csvs
from src.reasoner.support_type_reasoner import run_support_type_reasoner_on_all_csvs


JANE_PNR = "20000421-1234"


EXPECTED_GROUP_BY_TYPE = {
    "StudyGrant": "StudySupport",
    "StudyLoan": "StudySupport",
    "ActivitySupport": "WorkSupport",
}


def collect_reasoner_fields() -> tuple[set[tuple[str, str]], list[dict[str, Any]]]:
    """Run the reasoner and collect detected SupportType candidate fields."""

    results = run_support_type_reasoner_on_all_csvs()

    detected_fields: set[tuple[str, str]] = set()

    for file_result in results:
        source_file = file_result["source_file"]

        for field in file_result.get("support_type_fields", []):
            detected_fields.add((source_file, field["source_field"]))

    return detected_fields, results


def collect_mapping_fields() -> set[tuple[str, str]]:
    """Collect source_file/source_field pairs from support_type.json."""

    mapping_data = json.loads(MAPPINGS_FILE.read_text(encoding="utf-8"))

    mapping_fields: set[tuple[str, str]] = set()

    for rule in mapping_data["rules"]:
        if rule.get("target_class") == "SupportType":
            mapping_fields.add((rule["source_file"], rule["source_field"]))

    return mapping_fields


def print_reasoner_results(results: list[dict[str, Any]]) -> None:
    """Print reasoner output in a readable way."""

    print("\n" + "=" * 64)
    print("1. Reasoner output")
    print("=" * 64)

    for file_result in results:
        print(f"\nFile: {file_result['source_file']}")

        fields = file_result.get("support_type_fields", [])

        if not fields:
            print("  No SupportType candidate fields found.")
            continue

        for field in fields:
            print(
                f"  - {field['source_field']} "
                f"→ SupportType.{field['target_model_field']}, "
                f"confidence={field['confidence']}"
            )

            if field.get("source_description_field"):
                print(
                    f"    description field: "
                    f"{field['source_description_field']}"
                )

            if field.get("matched_values"):
                print(
                    f"    matched values: "
                    f"{', '.join(field['matched_values'])}"
                )

            if field.get("reason"):
                print(f"    reason: {field['reason']}")


def print_mapping_alignment(
    reasoner_fields: set[tuple[str, str]],
    mapping_fields: set[tuple[str, str]],
) -> None:
    """Compare reasoner-detected fields with mapping-rule fields."""

    print("\n" + "=" * 64)
    print("2. Reasoner ↔ mapper alignment")
    print("=" * 64)

    print("\nFields detected by reasoner:")
    for source_file, source_field in sorted(reasoner_fields):
        print(f"  - {source_file}.{source_field}")

    print("\nFields covered by mapper:")
    for source_file, source_field in sorted(mapping_fields):
        print(f"  - {source_file}.{source_field}")

    reasoner_without_mapping = reasoner_fields - mapping_fields
    mapping_without_reasoner = mapping_fields - reasoner_fields

    if reasoner_without_mapping:
        print("\n⚠ Reasoner found fields that do not currently have mapping rules:")
        for source_file, source_field in sorted(reasoner_without_mapping):
            print(f"  - {source_file}.{source_field}")
    else:
        print("\n✓ Every reasoner-detected field has a mapping rule.")

    if mapping_without_reasoner:
        print("\n⚠ Mapper has rules for fields the reasoner did not detect:")
        for source_file, source_field in sorted(mapping_without_reasoner):
            print(f"  - {source_file}.{source_field}")
    else:
        print("\n✓ Every mapping rule field was detected by the reasoner.")


def print_transformer_results() -> None:
    """Run the transformer for Jane and print the final SupportType objects."""

    print("\n" + "=" * 64)
    print("3. Transformer + Pydantic output for Jane")
    print("=" * 64)

    support_types = transform_support_type(JANE_PNR)

    if not support_types:
        raise AssertionError(f"No SupportType objects were created for {JANE_PNR}")

    print(f"\nFound {len(support_types)} SupportType object(s) for Jane:\n")

    for item in support_types:
        print(
            f"- {item.support_type.value} "
            f"({item.support_group.value})"
        )
        print(f"  source_file:       {item.source_file}")
        print(f"  source_field:      {item.source_field}")
        print(f"  source_record_id:  {item.source_record_id}")
        print(f"  source_value:      {item.source_value!r}")
        print(f"  description:       {item.source_description!r}")
        print(f"  mapping_rule_id:   {item.mapping_rule_id}")
        print(f"  rationale:         {item.mapping_rationale}")
        print()


def run_full_pipeline_check() -> None:
    """Run reasoner, compare mappings, then run transformer for Jane."""

    reasoner_fields, reasoner_results = collect_reasoner_fields()
    mapping_fields = collect_mapping_fields()

    print_reasoner_results(reasoner_results)
    print_mapping_alignment(reasoner_fields, mapping_fields)
    print_transformer_results()


def test_support_type_transformer_returns_results_for_jane() -> None:
    """Pytest test: Jane should have at least one SupportType result."""

    support_types = transform_support_type(JANE_PNR)

    assert support_types, f"Expected SupportType results for {JANE_PNR}"


def test_support_type_outputs_are_valid_and_traceable_for_jane() -> None:
    """Pytest test: every result should be valid and traceable."""

    support_types = transform_support_type(JANE_PNR)

    for item in support_types:
        assert item.support_type in SupportTypeValue
        assert item.support_group in SupportGroupValue

        assert item.source_value.strip()
        assert item.source_file.strip()
        assert item.source_field.strip()
        assert item.source_record_id.strip()
        assert item.mapping_rule_id.strip()

        expected_group = EXPECTED_GROUP_BY_TYPE[item.support_type.value]

        assert item.support_group.value == expected_group, (
            f"{item.support_type.value} should belong to {expected_group}, "
            f"not {item.support_group.value}"
        )


if __name__ == "__main__":
    run_full_pipeline_check()