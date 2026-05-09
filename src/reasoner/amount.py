from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"

DEFAULT_FILE = DATA_DIR / "fk_payment.csv"

CONFIDENCE_THRESHOLD = 0.6


AMOUNT_KEYWORDS = [
    "amount", "sum", "sek", "payment", "gross", "net",
    "belopp", "utbetalning", "ersättning"
]

WEEK_KEYWORDS = ["week", "weekly", "per_week", "vecka"]
MONTH_KEYWORDS = ["month", "monthly", "per_month", "månad"]
TOTAL_KEYWORDS = ["total", "sum", "period"]

NET_KEYWORDS = ["net", "after_tax", "netto"]
GROSS_KEYWORDS = ["gross", "before_tax", "brutto"]


def is_numeric_like(values: list[Any]) -> bool:
    checked = 0
    valid = 0

    for value in values:
        if value is None or value == "":
            continue

        checked += 1

        try:
            Decimal(str(value))
            valid += 1
        except (InvalidOperation, ValueError):
            pass

    if checked == 0:
        return False

    return valid / checked >= 0.8


def read_csv_samples(file_path: Path, sample_size: int = 20) -> dict[str, list[str]]:
    with open(file_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"No columns found in {file_path}")

        samples: dict[str, list[str]] = {
            column: [] for column in reader.fieldnames
        }

        for index, row in enumerate(reader):
            if index >= sample_size:
                break

            for column in reader.fieldnames:
                samples[column].append(row.get(column, ""))

    return samples


def classify_amount_column(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
    threshold: float = CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    column_text = column_name.lower()
    file_text = source_file.lower()

    score = 0.0
    reasons: list[str] = []
    scoring: list[dict[str, Any]] = []

    def add_score(signal: str, points: float, reason: str | None = None) -> None:
        nonlocal score

        score += points

        scoring.append({
            "signal": signal,
            "points": points,
            "running_score": round(max(score, 0.0), 2),
        })

        if reason:
            reasons.append(reason)

    # Positive signals
    if any(k in column_text for k in AMOUNT_KEYWORDS):
        add_score(
            "Column name contains amount keyword",
            0.6,
            "column name suggests monetary amount",
        )
    elif any(k in file_text for k in AMOUNT_KEYWORDS):
        add_score(
            "File name contains amount keyword",
            0.2,
            "file context suggests monetary data",
        )
    else:
        add_score(
            "No amount keyword found",
            0.0,
            None,
        )

    if is_numeric_like(sample_values):
        add_score(
            "Sample values are mostly numeric",
            0.3,
            "sample values are mostly numeric",
        )
    else:
        add_score(
            "Sample values are not mostly numeric",
            0.0,
            None,
        )

    if "sek" in column_text:
        currency = "SEK"
        add_score(
            "Currency inferred from 'sek'",
            0.2,
            "currency inferred from 'sek'",
        )
    else:
        currency = "SEK"
        add_score(
            "Currency defaulted to SEK",
            0.0,
            "currency defaulted to SEK",
        )

    # Negative signals
    negative_keywords = ["id", "date", "type", "code"]

    if any(k in column_text for k in negative_keywords):
        add_score(
            "Column name suggests identifier or metadata",
            -0.5,
            "column name suggests identifier or metadata",
        )

    # Frequency inference
    if any(k in column_text for k in WEEK_KEYWORDS):
        frequency = "Week"
        add_score(
            "Frequency inferred as Week",
            0.0,
            "frequency inferred as Week",
        )
    elif any(k in column_text for k in MONTH_KEYWORDS):
        frequency = "Month"
        add_score(
            "Frequency inferred as Month",
            0.0,
            "frequency inferred as Month",
        )
    elif any(k in column_text for k in TOTAL_KEYWORDS):
        frequency = "Total"
        add_score(
            "Frequency inferred as Total",
            0.0,
            "frequency inferred as Total",
        )
    else:
        frequency = None
        add_score(
            "Frequency unclear",
            0.0,
            "frequency unclear",
        )

    # Amount type inference
    if any(k in column_text for k in NET_KEYWORDS):
        amount_type = "Net"
        add_score(
            "Amount type inferred as Net",
            0.0,
            "amount type inferred as Net",
        )
    elif any(k in column_text for k in GROSS_KEYWORDS):
        amount_type = "Gross"
        add_score(
            "Amount type inferred as Gross",
            0.0,
            "amount type inferred as Gross",
        )
    else:
        amount_type = None
        add_score(
            "Amount type unclear",
            0.0,
            "amount type unclear",
        )

    confidence = round(max(score, 0.0), 2)
    selected = confidence >= threshold

    if selected:
        final_decision = (
            f"Selected as MonetaryAmount because confidence "
            f"{confidence} >= threshold {threshold}."
        )
    else:
        final_decision = (
            f"Rejected because confidence "
            f"{confidence} < threshold {threshold}."
        )

    return {
        "source_file": source_file,
        "source_field": column_name,
        "selected": selected,
        "target_concept": "MonetaryAmount" if selected else None,
        "currency": currency if selected else None,
        "frequency": frequency if selected else None,
        "amount_type": amount_type if selected else None,
        "confidence": confidence,
        "threshold": threshold,
        "scoring": scoring,
        "reason": "; ".join(reasons),
        "final_decision": final_decision,
    }


def run_reasoner_on_csv(file_path: Path = DEFAULT_FILE) -> list[dict[str, Any]]:
    if not file_path.exists():
        raise FileNotFoundError(f"CSV file not found: {file_path}")

    samples = read_csv_samples(file_path)
    results = []

    for column_name, sample_values in samples.items():
        result = classify_amount_column(
            source_file=file_path.name,
            column_name=column_name,
            sample_values=sample_values,
        )
        results.append(result)

    return results


def run_reasoner_on_all_csvs() -> list[dict[str, Any]]:
    all_results = []

    for file_path in DATA_DIR.glob("*.csv"):
        try:
            results = run_reasoner_on_csv(file_path)
            all_results.extend(results)
        except Exception as e:
            all_results.append({
                "source_file": file_path.name,
                "source_field": None,
                "selected": False,
                "target_concept": None,
                "currency": None,
                "frequency": None,
                "amount_type": None,
                "confidence": 0.0,
                "threshold": CONFIDENCE_THRESHOLD,
                "reason": f"Failed to process file: {e}",
                "final_decision": "Rejected because file could not be processed.",
            })

    return all_results


def print_results(results: list[dict[str, Any]]) -> None:
    selected = [r for r in results if r["selected"]]
    rejected = [r for r in results if not r["selected"]]

    print("=" * 72)
    print("Amount mapping reasoner")
    print("=" * 72)

    print()
    print("SELECTED MONETARY FIELDS")
    print("-" * 72)

    if not selected:
        print("No monetary fields selected.")

    for result in selected:
        print()
        print(f"File:          {result['source_file']}")
        print(f"Column:        {result['source_field']}")
        print(f"Concept:       {result['target_concept']}")
        print(f"Confidence:    {result['confidence']}")
        print("Score details:")
        for item in result["scoring"]:
            print(
                f"  {item['points']:+.2f}  "
                f"{item['signal']} "
                f"(running score: {item['running_score']})"
            )
        print(f"Currency:      {result['currency']}")
        print(f"Frequency:     {result['frequency']}")
        print(f"Amount type:   {result['amount_type']}")
        print(f"Reasoning:     {result['reason']}")
        print(f"Decision:      {result['final_decision']}")

    print()
    print("=" * 72)
    print("REJECTED / CONSIDERED FIELDS")
    print("-" * 72)

    for result in rejected:
        print()
        print(f"File:          {result['source_file']}")
        print(f"Column:        {result['source_field']}")
        print(f"Confidence:    {result['confidence']}")
        print("Score details:")
        for item in result["scoring"]:
            print(
                f"  {item['points']:+.2f}  "
                f"{item['signal']} "
                f"(running score: {item['running_score']})"
            )
        print(f"Reasoning:     {result['reason']}")
        print(f"Decision:      {result['final_decision']}")


if __name__ == "__main__":
    results = run_reasoner_on_all_csvs()
    print_results(results)