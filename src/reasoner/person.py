from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"

PERSON_FIELD_KEYWORDS = [
    "personal_id",
    "person_id",
    "personid",
    "pid",
    "personal number",
    "personnummer",
]

NEGATIVE_KEYWORDS = [
    "case_id", "amount", "sek", "pct", "scope", "status",
    "type", "code", "label", "description", "date", "week",
    "month", "from", "to", "start", "end"
]


def is_swedish_personal_id(value: str) -> bool:
    """
    Matches the synthetic Swedish personal number format:
    YYYYMMDD-XXXX
    """
    return bool(re.fullmatch(r"\d{8}-\d{4}", value.strip()))


def detect_person_id_format(values: list[Any]) -> tuple[bool, str | None]:
    checked = 0
    matches = 0

    for value in values:
        if value is None or value == "":
            continue

        text = str(value).strip()

        if text.lower() == "nan":
            continue

        checked += 1

        if is_swedish_personal_id(text):
            matches += 1

    if checked == 0:
        return False, None

    ratio = matches / checked

    if ratio >= 0.7:
        return True, "SwedishPersonalId"

    return False, None


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


def classify_person_field(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
) -> dict[str, Any]:
    column_text = column_name.lower()

    score = 0.0
    reasons: list[str] = []

    looks_like_person_by_name = any(
        keyword in column_text for keyword in PERSON_FIELD_KEYWORDS
    )

    if looks_like_person_by_name:
        score += 0.5
        reasons.append("column name suggests person identity information")

    is_person_like, person_id_format = detect_person_id_format(sample_values)

    if is_person_like:
        score += 0.5
        reasons.append(f"sample values match {person_id_format} format")

    if any(keyword in column_text for keyword in NEGATIVE_KEYWORDS):
        score -= 0.4
        reasons.append("column name suggests non-person metadata")

    is_person_field = score >= 0.6

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "Person" if is_person_field else None,
        "target_property": "personId" if is_person_field else None,
        "format": person_id_format if is_person_field else None,
        "confidence": round(max(score, 0.0), 2),
        "reason": "; ".join(reasons),
    }


def run_person_reasoner_on_csv(file_path: Path) -> dict[str, Any]:
    samples = read_csv_samples(file_path)

    fields = [
        classify_person_field(
            source_file=file_path.name,
            column_name=column,
            sample_values=values,
        )
        for column, values in samples.items()
    ]

    person_fields = [
        field for field in fields
        if field["target_concept"] == "Person"
    ]

    return {
        "source_file": file_path.name,
        "person_fields": person_fields,
    }


def run_person_reasoner_on_all_csvs(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    results = []

    for file_path in sorted(data_dir.glob("*.csv")):
        results.append(run_person_reasoner_on_csv(file_path))

    return results


def print_results(results: list[dict[str, Any]]) -> None:
    print("=" * 64)
    print("Person field mapping reasoner")
    print("=" * 64)

    for file_result in results:
        print()
        print(f"File: {file_result['source_file']}")

        if not file_result["person_fields"]:
            print("  No person fields found.")
            continue

        print("  Person fields:")
        for field in file_result["person_fields"]:
            print(
                f"    - {field['source_field']} "
                f"→ target=Person.personId, "
                f"format={field['format']}, "
                f"confidence={field['confidence']}"
            )


if __name__ == "__main__":
    results = run_person_reasoner_on_all_csvs()
    print_results(results)