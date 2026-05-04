from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"


OCCUPATION_FIELD_KEYWORDS = [
    "occupation", "employment", "employer", "job", "job_seeker",
    "registered", "category", "study", "student", "support",
    "grant", "decision", "pace", "scope"
]

JOB_SEEKER_KEYWORDS = [
    "job_seeker", "registered", "unemployed", "job seeker",
    "arbetsförmedlingen", "af", "category"
]

STUDENT_KEYWORDS = [
    "study", "student", "csn", "grant", "support", "study_pace",
    "study_mode", "education"
]

EMPLOYER_KEYWORDS = [
    "employer", "company", "organisation", "organization",
    "workplace"
]

SCOPE_KEYWORDS = [
    "scope", "pct", "percentage", "pace", "study_pace"
]

NEGATIVE_KEYWORDS = [
    "personal_id", "case_id", "decision_id", "amount", "sek",
    "date", "week", "month", "from", "to", "start", "end",
    "opened", "submission", "period"
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


def sample_values_contain(values: list[Any], keywords: list[str]) -> bool:
    for value in values:
        if value is None or value == "":
            continue

        text = str(value).strip().lower()

        if any(keyword in text for keyword in keywords):
            return True

    return False


def infer_occupation_type(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
) -> tuple[str | None, list[str]]:
    file_text = source_file.lower()
    column_text = column_name.lower()

    combined_text = f"{file_text} {column_text}"

    reasons: list[str] = []

    if any(keyword in combined_text for keyword in JOB_SEEKER_KEYWORDS):
        reasons.append("source file or column name suggests job seeker information")
        return "JobSeeker", reasons

    if sample_values_contain(sample_values, JOB_SEEKER_KEYWORDS):
        reasons.append("sample values suggest job seeker information")
        return "JobSeeker", reasons

    if any(keyword in combined_text for keyword in STUDENT_KEYWORDS):
        reasons.append("source file or column name suggests student information")
        return "Student", reasons

    if sample_values_contain(sample_values, STUDENT_KEYWORDS):
        reasons.append("sample values suggest student information")
        return "Student", reasons

    if any(keyword in combined_text for keyword in EMPLOYER_KEYWORDS):
        reasons.append("source file or column name suggests employer information")
        return "Employer", reasons

    if sample_values_contain(sample_values, EMPLOYER_KEYWORDS):
        reasons.append("sample values suggest employer information")
        return "Employer", reasons

    return None, reasons


def infer_occupation_role(column_name: str) -> str:
    text = column_name.lower()

    if any(keyword in text for keyword in SCOPE_KEYWORDS):
        return "scope"

    if "description" in text or "label" in text:
        return "description"

    if "type" in text or "category" in text or "status" in text:
        return "source_value"

    return "evidence"


def classify_occupation_field(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
) -> dict[str, Any]:
    file_text = source_file.lower()
    column_text = column_name.lower()

    score = 0.0
    reasons: list[str] = []

    looks_like_occupation_by_name = any(
        keyword in column_text for keyword in OCCUPATION_FIELD_KEYWORDS
    )

    if looks_like_occupation_by_name:
        score += 0.35
        reasons.append("column name suggests occupation/status information")

    occupation_type, occupation_reasons = infer_occupation_type(
        source_file=source_file,
        column_name=column_name,
        sample_values=sample_values,
    )

    if occupation_type is not None:
        score += 0.45
        reasons.extend(occupation_reasons)

    if any(keyword in file_text for keyword in ["af_job_seeker", "job_seeker"]):
        score += 0.25
        occupation_type = occupation_type or "JobSeeker"
        reasons.append("source file represents AF job seeker status")

    if any(keyword in file_text for keyword in ["csn", "study", "grant"]):
        score += 0.25
        occupation_type = occupation_type or "Student"
        reasons.append("source file represents CSN study support information")

    if any(keyword in column_text for keyword in SCOPE_KEYWORDS):
        score += 0.15
        reasons.append("column can describe occupation extent/scope")

    if any(keyword in column_text for keyword in NEGATIVE_KEYWORDS):
        score -= 0.35
        reasons.append("column name suggests non-occupation metadata")

    role = infer_occupation_role(column_name)

    if role == "scope":
        reasons.append("field role inferred as occupation scope")
    elif role == "description":
        reasons.append("field role inferred as occupation description")
    elif role == "source_value":
        reasons.append("field role inferred as source occupation value")
    else:
        reasons.append("field role inferred as supporting evidence")

    is_occupation_field = score >= 0.55 and occupation_type is not None

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "OccupationField" if is_occupation_field else None,
        "occupation_type": occupation_type if is_occupation_field else None,
        "role": role if is_occupation_field else None,
        "confidence": round(max(score, 0.0), 2),
        "reason": "; ".join(reasons),
    }


def find_occupation_mappings(
    occupation_fields: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    mappings = []

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}

    for field in occupation_fields:
        key = (field["source_file"], field["occupation_type"])
        grouped.setdefault(key, []).append(field)

    for (source_file, occupation_type), fields in grouped.items():
        value_fields = [
            field for field in fields
            if field["role"] in ["source_value", "evidence"]
        ]

        scope_fields = [
            field for field in fields
            if field["role"] == "scope"
        ]

        description_fields = [
            field for field in fields
            if field["role"] == "description"
        ]

        for value_field in value_fields:
            confidence = value_field["confidence"]

            if scope_fields:
                confidence = round(
                    (confidence + max(f["confidence"] for f in scope_fields)) / 2,
                    2,
                )

            mappings.append({
                "source_file": source_file,
                "target_concept": "Occupation",
                "source_field": value_field["source_field"],
                "scope_field": (
                    scope_fields[0]["source_field"]
                    if scope_fields else None
                ),
                "description_field": (
                    description_fields[0]["source_field"]
                    if description_fields else None
                ),
                "target_property": "occupationType",
                "target_value": occupation_type,
                "confidence": confidence,
                "reason": (
                    f"Mapped {value_field['source_field']} to Occupation "
                    f"because it provides source evidence for the ontology "
                    f"occupation type {occupation_type}."
                ),
            })

    return mappings


def run_occupation_reasoner_on_csv(file_path: Path) -> dict[str, Any]:
    samples = read_csv_samples(file_path)

    fields = [
        classify_occupation_field(
            source_file=file_path.name,
            column_name=column,
            sample_values=values,
        )
        for column, values in samples.items()
    ]

    occupation_fields = [
        field for field in fields
        if field["target_concept"] == "OccupationField"
    ]

    occupation_mappings = find_occupation_mappings(occupation_fields)

    return {
        "source_file": file_path.name,
        "occupation_fields": occupation_fields,
        "occupation_mappings": occupation_mappings,
    }


def run_occupation_reasoner_on_all_csvs(
    data_dir: Path = DATA_DIR,
) -> list[dict[str, Any]]:
    results = []

    for file_path in sorted(data_dir.glob("*.csv")):
        results.append(run_occupation_reasoner_on_csv(file_path))

    return results


def print_results(results: list[dict[str, Any]]) -> None:
    print("=" * 64)
    print("Occupation mapping reasoner")
    print("=" * 64)

    for file_result in results:
        print()
        print(f"File: {file_result['source_file']}")

        if not file_result["occupation_fields"]:
            print("  No occupation fields found.")
            continue

        print("  Occupation fields:")
        for field in file_result["occupation_fields"]:
            print(
                f"    - {field['source_field']} "
                f"→ occupation_type={field['occupation_type']}, "
                f"role={field['role']}, "
                f"confidence={field['confidence']}"
            )

        if file_result["occupation_mappings"]:
            print("  Occupation mappings:")
            for mapping in file_result["occupation_mappings"]:
                print(
                    f"    - {mapping['source_field']} "
                    f"→ {mapping['target_value']} "
                    f"confidence={mapping['confidence']}"
                )


if __name__ == "__main__":
    results = run_occupation_reasoner_on_all_csvs()
    print_results(results)