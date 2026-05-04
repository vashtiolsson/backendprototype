from __future__ import annotations

import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"

TIME_FIELD_KEYWORDS = [
    "date", "month", "week", "from", "to", "start", "end",
    "registered", "deregistered", "opened", "submission", "period"
]

START_KEYWORDS = ["from", "start", "registered", "opened"]
END_KEYWORDS = ["to", "end", "deregistered"]
POINT_IN_TIME_KEYWORDS = ["date", "month", "submission", "opened"]

NEGATIVE_KEYWORDS = [
    "personal_id", "case_id", "amount", "sek", "pct", "scope",
    "status", "type", "code", "label", "description"
]


def is_iso_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def is_compact_date(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y%m%d")
        return True
    except ValueError:
        return False


def is_year_month(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}-\d{2}", value))


def is_year_week(value: str) -> bool:
    return bool(re.fullmatch(r"\d{6}", value))


def detect_time_format(values: list[Any]) -> tuple[bool, str | None]:
    checked = 0
    matches = {
        "Date": 0,
        "CompactDate": 0,
        "YearMonth": 0,
        "YearWeek": 0,
    }

    for value in values:
        if value is None or value == "":
            continue

        text = str(value).strip()

        if text.lower() == "nan":
            continue

        checked += 1

        if is_iso_date(text):
            matches["Date"] += 1
        elif is_compact_date(text):
            matches["CompactDate"] += 1
        elif is_year_month(text):
            matches["YearMonth"] += 1
        elif is_year_week(text):
            matches["YearWeek"] += 1

    if checked == 0:
        return False, None

    best_format = max(matches, key=matches.get)
    ratio = matches[best_format] / checked

    if ratio >= 0.7:
        return True, best_format

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


def infer_time_role(column_name: str) -> str:
    text = column_name.lower()

    if any(keyword in text for keyword in START_KEYWORDS):
        return "start"

    if any(keyword in text for keyword in END_KEYWORDS):
        return "end"

    if "week" in text:
        if "start" in text:
            return "start"
        if "end" in text:
            return "end"

    return "point_in_time"


def classify_time_field(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
) -> dict[str, Any]:
    column_text = column_name.lower()

    score = 0.0
    reasons: list[str] = []

    looks_like_time_by_name = any(
        keyword in column_text for keyword in TIME_FIELD_KEYWORDS
    )

    if looks_like_time_by_name:
        score += 0.4
        reasons.append("column name suggests time/period information")

    is_time_like, time_format = detect_time_format(sample_values)

    if is_time_like:
        score += 0.5
        reasons.append(f"sample values match {time_format} format")

    if any(keyword in column_text for keyword in NEGATIVE_KEYWORDS):
        score -= 0.5
        reasons.append("column name suggests non-time metadata")

    role = infer_time_role(column_name)

    if role in ["start", "end"]:
        score += 0.1
        reasons.append(f"field role inferred as period {role}")
    else:
        reasons.append("field role inferred as point in time")

    is_time_field = score >= 0.6

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "TimeField" if is_time_field else None,
        "role": role if is_time_field else None,
        "format": time_format if is_time_field else None,
        "confidence": round(max(score, 0.0), 2),
        "reason": "; ".join(reasons),
    }


def find_period_pairs(time_fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    starts = [f for f in time_fields if f["role"] == "start"]
    ends = [f for f in time_fields if f["role"] == "end"]

    pairs = []

    for start in starts:
        for end in ends:
            if start["source_file"] != end["source_file"]:
                continue

            confidence = round(
                (start["confidence"] + end["confidence"]) / 2,
                2,
            )

            pairs.append({
                "source_file": start["source_file"],
                "target_concept": "TimePeriod",
                "start_field": start["source_field"],
                "end_field": end["source_field"],
                "confidence": confidence,
                "reason": (
                    f"Paired {start['source_field']} with {end['source_field']} "
                    f"because they are start/end time fields in the same file."
                ),
            })

    return pairs


def run_time_reasoner_on_csv(file_path: Path) -> dict[str, Any]:
    samples = read_csv_samples(file_path)

    fields = [
        classify_time_field(
            source_file=file_path.name,
            column_name=column,
            sample_values=values,
        )
        for column, values in samples.items()
    ]

    time_fields = [
        field for field in fields
        if field["target_concept"] == "TimeField"
    ]

    period_pairs = find_period_pairs(time_fields)

    return {
        "source_file": file_path.name,
        "time_fields": time_fields,
        "period_pairs": period_pairs,
    }


def run_time_reasoner_on_all_csvs(data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    results = []

    for file_path in sorted(data_dir.glob("*.csv")):
        results.append(run_time_reasoner_on_csv(file_path))

    return results


def print_results(results: list[dict[str, Any]]) -> None:
    print("=" * 64)
    print("Time field mapping reasoner")
    print("=" * 64)

    for file_result in results:
        print()
        print(f"File: {file_result['source_file']}")

        if not file_result["time_fields"]:
            print("  No time fields found.")
            continue

        print("  Time fields:")
        for field in file_result["time_fields"]:
            print(
                f"    - {field['source_field']} "
                f"→ role={field['role']}, "
                f"format={field['format']}, "
                f"confidence={field['confidence']}"
            )

        if file_result["period_pairs"]:
            print("  Period pairs:")
            for pair in file_result["period_pairs"]:
                print(
                    f"    - {pair['start_field']} → {pair['end_field']} "
                    f"confidence={pair['confidence']}"
                )


if __name__ == "__main__":
    results = run_time_reasoner_on_all_csvs()
    print_results(results)