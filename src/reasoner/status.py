from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"


STATUS_FIELD_KEYWORDS = [
    "status", "state", "registered", "approved", "active",
    "inactive", "initiated", "planned", "submitted", "decision"
]

STATUS_VALUE_MAP = {
    "active": "Active",
    "approved": "Approved",
    "inactive": "Inactive",
    "initiated": "Initiated",
    "planned": "Planned",
    "submitted": "Initiated",
    "pending": "Initiated",
    "open": "Active",
    "closed": "Inactive",
    "true": "Active",
    "false": "Inactive",
    "paid": "Approved",
}

NEGATIVE_KEYWORDS = [
    "personal_id", "case_id", "decision_id", "amount", "sek",
    "date", "week", "month", "from", "to", "start", "end",
    "period", "pct", "scope", "description", "type", "category"
]


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


def normalize_value(value: Any) -> str | None:
    if value is None or value == "":
        return None

    text = str(value).strip().lower()

    if text == "nan":
        return None

    return text


def infer_status_values(sample_values: list[Any]) -> tuple[dict[str, str], list[str]]:
    """
    Infer ontology Status values from source sample values.
    Returns a source-value → ontology-value map.
    """
    value_map: dict[str, str] = {}
    reasons: list[str] = []

    for value in sample_values:
        text = normalize_value(value)

        if text is None:
            continue

        if text in STATUS_VALUE_MAP:
            value_map[text] = STATUS_VALUE_MAP[text]
            reasons.append(f"sample value {text!r} maps to {STATUS_VALUE_MAP[text]}")

    return value_map, reasons


def infer_status_role(column_name: str) -> str:
    text = column_name.lower()

    if "description" in text or "label" in text:
        return "description"

    if "status" in text or "state" in text or "registered" in text:
        return "source_value"

    if "decision" in text:
        return "decision_evidence"

    return "evidence"


def classify_status_field(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
) -> dict[str, Any]:
    column_text = column_name.lower()

    score = 0.0
    reasons: list[str] = []

    looks_like_status_by_name = any(
        keyword in column_text for keyword in STATUS_FIELD_KEYWORDS
    )

    if looks_like_status_by_name:
        score += 0.4
        reasons.append("column name suggests lifecycle/status information")

    value_map, value_reasons = infer_status_values(sample_values)

    if value_map:
        score += 0.45
        reasons.extend(value_reasons)

    if "registered" in column_text:
        score += 0.15
        reasons.append("registered flag can indicate Active or Inactive status")

    if "decision" in column_text and value_map:
        score += 0.1
        reasons.append("decision field contains status-like values")

    if any(keyword in column_text for keyword in NEGATIVE_KEYWORDS):
        score -= 0.35
        reasons.append("column name suggests non-status metadata")

    role = infer_status_role(column_name)

    if role == "description":
        reasons.append("field role inferred as status description")
    elif role == "source_value":
        reasons.append("field role inferred as source status value")
    elif role == "decision_evidence":
        reasons.append("field role inferred as decision status evidence")
    else:
        reasons.append("field role inferred as supporting evidence")

    is_status_field = score >= 0.55 and bool(value_map)

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "StatusField" if is_status_field else None,
        "role": role if is_status_field else None,
        "target_value_map": value_map if is_status_field else None,
        "confidence": round(max(score, 0.0), 2),
        "reason": "; ".join(reasons),
    }


def find_status_mappings(
    status_fields: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mappings = []

    for field in status_fields:
        mappings.append({
            "source_file": field["source_file"],
            "target_concept": "Status",
            "source_field": field["source_field"],
            "target_property": "statusType",
            "target_value_map": field["target_value_map"],
            "confidence": field["confidence"],
            "reason": (
                f"Mapped {field['source_field']} to Status because it contains "
                f"source values that correspond to ontology lifecycle states."
            ),
        })

    return mappings


def run_status_reasoner_on_csv(file_path: Path) -> dict[str, Any]:
    samples = read_csv_samples(file_path)

    fields = [
        classify_status_field(
            source_file=file_path.name,
            column_name=column,
            sample_values=values,
        )
        for column, values in samples.items()
    ]

    status_fields = [
        field for field in fields
        if field["target_concept"] == "StatusField"
    ]

    status_mappings = find_status_mappings(status_fields)

    return {
        "source_file": file_path.name,
        "status_fields": status_fields,
        "status_mappings": status_mappings,
    }


def run_status_reasoner_on_all_csvs(
    data_dir: Path = DATA_DIR,
) -> list[dict[str, Any]]:
    results = []

    for file_path in sorted(data_dir.glob("*.csv")):
        results.append(run_status_reasoner_on_csv(file_path))

    return results


def print_results(results: list[dict[str, Any]]) -> None:
    print("=" * 64)
    print("Status mapping reasoner")
    print("=" * 64)

    for file_result in results:
        print()
        print(f"File: {file_result['source_file']}")

        if not file_result["status_fields"]:
            print("  No status fields found.")
            continue

        print("  Status fields:")
        for field in file_result["status_fields"]:
            print(
                f"    - {field['source_field']} "
                f"→ role={field['role']}, "
                f"values={field['target_value_map']}, "
                f"confidence={field['confidence']}"
            )

        if file_result["status_mappings"]:
            print("  Status mappings:")
            for mapping in file_result["status_mappings"]:
                print(
                    f"    - {mapping['source_field']} "
                    f"→ {mapping['target_value_map']} "
                    f"confidence={mapping['confidence']}"
                )


if __name__ == "__main__":
    results = run_status_reasoner_on_all_csvs()
    print_results(results)