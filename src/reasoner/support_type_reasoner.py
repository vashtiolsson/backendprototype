from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"


SUPPORT_TYPE_FIELD_PATTERNS = {
    "benefit_type": 0.6,
    "benefit_group": 0.55,
    "benefit_group_code": 0.6,
    "support_type": 0.6,
    "support_form": 0.55,
    "support_form_code": 0.6,
    "amount_type": 0.6,
    "amount_type_code": 0.65,
    "grant_code": 0.6,
    "decision_type": 0.35,
}


NEGATIVE_EXACT_FIELDS = {
    "personal_id",
    "case_id",
    "decision_id",
    "payment_id",
    "date",
    "start_date",
    "end_date",
    "week",
    "month",
    "amount",
    "amount_sek",
    "total_amount",
    "currency",
    "sek",
    "pct",
    "scope",
    "status",
}


DESCRIPTION_OR_LABEL_KEYWORDS = [
    "description",
    "label",
    "text",
    "name",
]


KNOWN_SUPPORT_VALUES = {
    "activity support",
    "fk:as",
    "student_grant",
    "study grant",
    "study loan",
    "grant",
    "loan",
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


def normalize_text(value: Any) -> str:
    return str(value).strip().lower()


def detect_support_type_values(values: list[Any]) -> tuple[bool, float, list[str]]:
    checked = 0
    matches = 0
    matched_values: list[str] = []

    for value in values:
        if value is None or value == "":
            continue

        text = normalize_text(value)

        if text == "nan":
            continue

        checked += 1

        if text in KNOWN_SUPPORT_VALUES:
            matches += 1
            if text not in matched_values:
                matched_values.append(text)

    if checked == 0:
        return False, 0.0, []

    ratio = matches / checked

    return ratio >= 0.3, ratio, matched_values


def score_column_name(column_name: str) -> tuple[float, list[str]]:
    column_text = column_name.lower()

    score = 0.0
    reasons: list[str] = []

    for pattern, weight in SUPPORT_TYPE_FIELD_PATTERNS.items():
        if pattern in column_text:
            score += weight
            reasons.append(f"column name matches support-type pattern '{pattern}'")
            break

    if column_text in NEGATIVE_EXACT_FIELDS:
        score -= 0.5
        reasons.append("column name is known non-support metadata")

    if any(keyword in column_text for keyword in DESCRIPTION_OR_LABEL_KEYWORDS):
        score -= 0.35
        reasons.append("column appears to be descriptive text rather than the source value")

    return score, reasons


def classify_support_type_field(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
) -> dict[str, Any]:
    score, reasons = score_column_name(column_name)

    is_support_like, ratio, matched_values = detect_support_type_values(sample_values)

    if is_support_like:
        value_score = min(0.35, ratio * 0.5)
        score += value_score
        reasons.append(
            f"sample values match known support-type values "
            f"(ratio={round(ratio, 2)})"
        )

    confidence = round(max(min(score, 1.0), 0.0), 2)

    is_support_field = confidence >= 0.6

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "SupportType" if is_support_field else None,
        "target_model_field": "source_value" if is_support_field else None,
        "ontology_class": "SupportType" if is_support_field else None,
        "confidence": confidence,
        "matched_values": matched_values,
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
    data_dir: Path = DATA_DIR,
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
            print("  No SupportType fields found.")
            continue

        print("  SupportType candidate fields:")

        for field in file_result["support_type_fields"]:
            print(
                f"    - {field['source_field']} "
                f"→ target=SupportType.source_value, "
                f"confidence={field['confidence']}"
            )

            if field["matched_values"]:
                print(
                    f"      matched values: {', '.join(field['matched_values'])}"
                )

            if field["reason"]:
                print(f"      reason: {field['reason']}")


if __name__ == "__main__":
    results = run_support_type_reasoner_on_all_csvs()
    print_results(results)