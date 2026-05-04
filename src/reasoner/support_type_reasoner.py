from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"


SUPPORT_TYPE_FIELD_KEYWORDS = [
    "benefit_type",
    "benefit_group",
    "support_type",
    "support_form",
    "amount_type",
    "grant_code",
]

NEGATIVE_KEYWORDS = [
    "personal_id", "case_id", "date", "week", "month",
    "amount", "sek", "pct", "scope", "status",
    "description", "label"
]


KNOWN_SUPPORT_VALUES = {
    "activity support",
    "fk:as",
    "student_grant",
    "grund",
    "grundb",
    "grundl",
}


def read_csv_samples(file_path: Path, sample_size: int = 30) -> dict[str, list[str]]:
    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"No columns found in {file_path}")

        samples = {column: [] for column in reader.fieldnames}

        for index, row in enumerate(reader):
            if index >= sample_size:
                break

            for column in reader.fieldnames:
                samples[column].append(row.get(column, ""))

    return samples


def detect_support_type_values(values: list[Any]) -> tuple[bool, float]:
    checked = 0
    matches = 0

    for value in values:
        if value is None or value == "":
            continue

        text = str(value).strip().lower()

        if text == "nan":
            continue

        checked += 1

        if text in KNOWN_SUPPORT_VALUES:
            matches += 1

    if checked == 0:
        return False, 0.0

    ratio = matches / checked

    return ratio >= 0.5, ratio


def classify_support_type_field(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
) -> dict[str, Any]:
    column_text = column_name.lower()

    score = 0.0
    reasons: list[str] = []

    # Name-based detection
    if any(keyword in column_text for keyword in SUPPORT_TYPE_FIELD_KEYWORDS):
        score += 0.5
        reasons.append("column name suggests support/benefit type")

    # Value-based detection
    is_support_like, ratio = detect_support_type_values(sample_values)

    if is_support_like:
        score += 0.4
        reasons.append(f"sample values match known support types (ratio={round(ratio,2)})")

    # Negative signal
    if any(keyword in column_text for keyword in NEGATIVE_KEYWORDS):
        score -= 0.4
        reasons.append("column name suggests non-support metadata")

    is_support_field = score >= 0.6

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "SupportType" if is_support_field else None,
        "target_property": "supportType" if is_support_field else None,
        "confidence": round(max(score, 0.0), 2),
        "reason": "; ".join(reasons),
    }


def run_support_type_reasoner_on_csv(file_path: Path) -> dict[str, Any]:
    samples = read_csv_samples(file_path)

    fields = [
        classify_support_type_field(
            source_file=file_path.name,
            column_name=column,
            sample_values=values,
        )
        for column, values in samples.items()
    ]

    support_fields = [
        field for field in fields
        if field["target_concept"] == "SupportType"
    ]

    return {
        "source_file": file_path.name,
        "support_type_fields": support_fields,
    }


def run_support_type_reasoner_on_all_csvs(
    data_dir: Path = DATA_DIR
) -> list[dict[str, Any]]:
    results = []

    for file_path in sorted(data_dir.glob("*.csv")):
        results.append(run_support_type_reasoner_on_csv(file_path))

    return results


def print_results(results: list[dict[str, Any]]) -> None:
    print("=" * 64)
    print("SupportType field mapping reasoner")
    print("=" * 64)

    for file_result in results:
        print()
        print(f"File: {file_result['source_file']}")

        if not file_result["support_type_fields"]:
            print("  No support type fields found.")
            continue

        print("  SupportType fields:")
        for field in file_result["support_type_fields"]:
            print(
                f"    - {field['source_field']} "
                f"→ target=SupportType.supportType, "
                f"confidence={field['confidence']}"
            )


if __name__ == "__main__":
    results = run_support_type_reasoner_on_all_csvs()
    print_results(results)