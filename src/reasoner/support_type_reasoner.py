from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"

MAX_REASONER_CONFIDENCE = 0.95


SUPPORT_TYPE_FIELD_PATTERNS = {
    "benefit_type": 0.65,
    "benefit_group_code": 0.65,
    "benefit_group": 0.55,
    "support_type": 0.65,
    "support_form_code": 0.65,
    "support_form": 0.55,
    "amount_type_code": 0.65,
    "amount_type": 0.55,
    "grant_code": 0.60,
    "decision_type": 0.35,
}


NEGATIVE_EXACT_FIELDS = {
    "personal_id",
    "person_id",
    "pnr",
    "case_id",
    "decision_id",
    "payment_id",
    "period_id",
    "date",
    "start_date",
    "end_date",
    "week",
    "month",
    "amount",
    "amount_sek",
    "total_amount",
    "total_amount_sek",
    "gross_amount_sek",
    "net_amount_sek",
    "tax_withheld_sek",
    "currency",
    "sek",
    "pct",
    "scope",
    "status",
    "case_status",
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
    "as",
    "student_grant",
    "study_grant",
    "student_loan",
    "study_loan",
    "grant",
    "loan",
    "grund",
    "grundb",
    "grundl",
}


def _read_csv(file_path: Path) -> list[dict[str, Any]]:
    """Read a CSV file into row dictionaries."""

    with open(file_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def read_csv_samples(file_path: Path, sample_size: int = 30) -> dict[str, list[str]]:
    """Read a small sample of values from each CSV column."""

    with open(file_path, encoding="utf-8-sig", newline="") as f:
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
    """Normalize a value for comparison."""

    return str(value).strip().lower()


def is_description_or_label_field(column_name: str) -> bool:
    """Check whether a field looks like a description/label field."""

    column_text = column_name.lower()

    return any(
        keyword in column_text
        for keyword in DESCRIPTION_OR_LABEL_KEYWORDS
    )


def detect_support_type_values(values: list[Any]) -> tuple[bool, float, list[str]]:
    """
    Check whether sample values look like known SupportType values.

    Returns:
      - whether the column appears support-like
      - match ratio
      - matched values
    """

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

    return ratio >= 0.30, ratio, matched_values


def score_column_name(column_name: str) -> tuple[float, list[str]]:
    """Score a column based on whether its name suggests SupportType."""

    column_text = column_name.lower()

    score = 0.0
    reasons: list[str] = []

    for pattern, weight in SUPPORT_TYPE_FIELD_PATTERNS.items():
        if pattern in column_text:
            score += weight
            reasons.append(f"column name matches support-type pattern '{pattern}'")
            break

    if column_text in NEGATIVE_EXACT_FIELDS:
        score -= 0.50
        reasons.append("column name is known non-support metadata")

    if is_description_or_label_field(column_name):
        score -= 0.35
        reasons.append(
            "column appears to be descriptive text rather than the source value"
        )

    return score, reasons


def infer_description_field(
    source_field: str,
    all_columns: list[str],
) -> str | None:
    """
    Try to find a human-readable description field connected to the source field.
    """

    source_lower = source_field.lower()
    columns_by_lower = {column.lower(): column for column in all_columns}

    candidates: list[str] = []

    specific_candidates = {
        "amount_type_code": [
            "amount_type_label",
            "amount_type_description",
        ],
        "support_form_code": [
            "support_form_description",
            "support_form_label",
        ],
        "benefit_group_code": [
            "benefit_group_description",
            "benefit_group_label",
        ],
        "grant_code": [
            "grant_description",
            "grant_label",
        ],
        "benefit_type": [
            "benefit_type_description",
            "benefit_type_label",
        ],
        "support_type": [
            "support_type_description",
            "support_type_label",
        ],
    }

    candidates.extend(specific_candidates.get(source_lower, []))

    if source_lower.endswith("_code"):
        stem = source_lower.removesuffix("_code")
        candidates.extend(
            [
                f"{stem}_label",
                f"{stem}_description",
                f"{stem}_text",
                f"{stem}_name",
            ]
        )

    if source_lower.endswith("_type"):
        candidates.extend(
            [
                f"{source_lower}_label",
                f"{source_lower}_description",
            ]
        )

    for candidate in candidates:
        if candidate in columns_by_lower:
            return columns_by_lower[candidate]

    return None


def suggest_support_type_value_map(sample_values: list[Any]) -> dict[str, str]:
    """
    Suggest source-value to ontology-value mappings.

    These are suggestions only. The frontend Mapping Workbench can edit them.
    """

    suggestions: dict[str, str] = {}

    known_values = {
        "GRUNDB": "StudyGrant",
        "GRUNDL": "StudyLoan",
        "AS": "ActivitySupport",
        "Activity support": "ActivitySupport",
        "activity support": "ActivitySupport",
        "Study grant": "StudyGrant",
        "Study loan": "StudyLoan",
        "student_grant": "StudyGrant",
        "student_loan": "StudyLoan",
        "study_grant": "StudyGrant",
        "study_loan": "StudyLoan",
        "grant": "StudyGrant",
        "loan": "StudyLoan",
    }

    for value in sample_values:
        if value is None or value == "":
            continue

        text_value = str(value).strip()

        if text_value in suggestions:
            continue

        suggestions[text_value] = known_values.get(text_value, "UnknownNeedsReview")

    return suggestions


def classify_support_type_field(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
    all_columns: list[str],
) -> dict[str, Any]:
    """
    Classify whether a CSV column is likely to contain SupportType source values.

    The reasoner does not create the final SupportType object.
    It only identifies candidate source fields for the mapper/transformer.
    """

    score, reasons = score_column_name(column_name)

    is_support_like, ratio, matched_values = detect_support_type_values(sample_values)

    if is_support_like:
        value_score = min(0.35, ratio * 0.50)
        score += value_score
        reasons.append(
            f"sample values match known support-type values "
            f"(ratio={round(ratio, 2)})"
        )

    confidence = round(
        max(min(score, MAX_REASONER_CONFIDENCE), 0.0),
        2,
    )

    is_main_source_value_field = (
        confidence >= 0.60
        and not is_description_or_label_field(column_name)
    )

    source_description_field = None

    if is_main_source_value_field:
        source_description_field = infer_description_field(
            source_field=column_name,
            all_columns=all_columns,
        )

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "SupportType" if is_main_source_value_field else None,
        "target_model_field": "source_value" if is_main_source_value_field else None,
        "ontology_class": "SupportType" if is_main_source_value_field else None,
        "source_description_field": source_description_field,
        "confidence": confidence,
        "matched_values": matched_values,
        "reason": "; ".join(reasons),
        "reasons": reasons,
        "scoring": [
            {
                "type": "field_name_and_value_match",
                "score": confidence,
                "explanation": "; ".join(reasons),
            }
        ],
        "is_main_source_value_field": is_main_source_value_field,
    }


def run_support_type_reasoner(
    person_id: str = "20000421-1234",
    data_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """
    Run the SupportType reasoner on uploaded or raw CSV files.

    This is the function imported by api.py.
    It returns frontend-ready fields for the Mapping Workbench.
    """

    if data_dir is None:
        data_dir = DATA_DIR

    print(f"[REASONER] Scanning folder: {data_dir}", flush=True)
    print(f"[REASONER] Looking for person_id: {person_id}", flush=True)

    fields: list[dict[str, Any]] = []
    considered_fields: list[dict[str, Any]] = []
    other_fields: list[dict[str, Any]] = []

    csv_files = sorted(data_dir.glob("*.csv"))

    print(f"[REASONER] CSV files found: {len(csv_files)}", flush=True)

    for csv_file in csv_files:
        print(f"[REASONER] Reading file: {csv_file.name}", flush=True)

        rows = _read_csv(csv_file)

        if not rows:
            print(f"[REASONER] Skipped empty file: {csv_file.name}", flush=True)
            continue

        all_columns = list(rows[0].keys())

        person_rows = [
            row for row in rows
            if row.get("personal_id") == person_id
            or row.get("person_id") == person_id
            or row.get("pnr") == person_id
        ]

        print(
            f"[REASONER] Rows for person in {csv_file.name}: {len(person_rows)}",
            flush=True,
        )

        # Prefer Jane/person-specific rows.
        # If this file does not contain Jane, fall back to all rows so the file
        # can still be inspected.
        sample_rows = person_rows if person_rows else rows

        for column_name in all_columns:
            sample_values = [
                row.get(column_name)
                for row in sample_rows
                if row.get(column_name) not in [None, ""]
            ]

            if not sample_values:
                continue

            classification = classify_support_type_field(
                source_file=csv_file.name,
                column_name=column_name,
                sample_values=sample_values[:30],
                all_columns=all_columns,
            )

            confidence = classification.get("confidence", 0)

            if classification.get("is_main_source_value_field"):
                print(
                    f"[REASONER] ACCEPTED: {csv_file.name}.{column_name} "
                    f"confidence={confidence}",
                    flush=True,
                )

                fields.append(
                    {
                        "id": len(fields),
                        "name": column_name,
                        "file": csv_file.name,
                        "type": "categorical",
                        "status": "accepted",
                        "color": "teal",
                        "concept": "SupportType",
                        "confidence": confidence,
                        "threshold": 0.6,
                        "samples": sample_values[:10],
                        "source_values": sorted(set(str(v) for v in sample_values)),
                        "suggested_target_value_map": suggest_support_type_value_map(
                            sample_values
                        ),
                        "rationale": classification.get("reason", ""),
                        "scoring": classification.get("scoring", []),
                        "source_description_field": classification.get(
                            "source_description_field"
                        ),
                        "mapping_rule_id": (
                            f"{csv_file.stem}_{column_name}_to_support_type"
                        ),
                    }
                )
            else:
                considered_fields.append(
                    {
                        "file": csv_file.name,
                        "field": column_name,
                        "confidence": confidence,
                        "samples": sample_values[:5],
                        "whyRejected": "Not selected as main SupportType field.",
                        "rationale": classification.get("reason", ""),
                    }
                )

    print(f"[REASONER] Finished. Accepted fields: {len(fields)}", flush=True)

    return {
        "fields": fields,
        "considered_fields": considered_fields,
        "other_fields": other_fields,
    }


def run_support_type_reasoner_on_csv(file_path: Path) -> dict[str, Any]:
    """Run the SupportType reasoner on one CSV file."""

    samples = read_csv_samples(file_path)
    all_columns = list(samples.keys())

    fields = [
        classify_support_type_field(
            source_file=file_path.name,
            column_name=column,
            sample_values=values,
            all_columns=all_columns,
        )
        for column, values in samples.items()
    ]

    support_fields = [
        field
        for field in fields
        if field["target_concept"] == "SupportType"
    ]

    return {
        "source_file": file_path.name,
        "support_type_fields": support_fields,
    }


def run_support_type_reasoner_on_all_csvs(
    data_dir: Path = DATA_DIR,
) -> list[dict[str, Any]]:
    """Run the SupportType reasoner on all CSV files in data/raw."""

    results = []

    for file_path in sorted(data_dir.glob("*.csv")):
        results.append(run_support_type_reasoner_on_csv(file_path))

    return results


def print_results(results: list[dict[str, Any]]) -> None:
    """Print reasoner results in a readable format."""

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
                f"→ target=SupportType.{field['target_model_field']}, "
                f"confidence={field['confidence']}"
            )

            if field["source_description_field"]:
                print(
                    f"      description field: "
                    f"{field['source_description_field']}"
                )

            if field["matched_values"]:
                print(
                    f"      matched values: "
                    f"{', '.join(field['matched_values'])}"
                )

            if field["reason"]:
                print(f"      reason: {field['reason']}")


if __name__ == "__main__":
    results = run_support_type_reasoner_on_all_csvs()
    print_results(results)