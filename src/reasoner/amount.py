from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"

DEFAULT_FILE = DATA_DIR / "fk_payment.csv"


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
    sample_values: list,
) -> dict:
    column_text = column_name.lower()
    file_text = source_file.lower()

    score = 0.0
    reasons = []

    # ── Positive signals ─────────────────────────────────────

    # Strong signal: column name
    if any(k in column_text for k in AMOUNT_KEYWORDS):
        score += 0.6
        reasons.append("column name suggests monetary amount")

    # Weak signal: file context
    elif any(k in file_text for k in AMOUNT_KEYWORDS):
        score += 0.2
        reasons.append("file context suggests monetary data")

    # Numeric values
    if is_numeric_like(sample_values):
        score += 0.3
        reasons.append("sample values are mostly numeric")

    # Currency inference
    if "sek" in column_text:
        currency = "SEK"
        score += 0.2
        reasons.append("currency inferred from 'sek'")
    else:
        currency = "SEK"
        reasons.append("currency defaulted to SEK")

    # ── Negative signals (very important) ─────────────────────

    NEGATIVE_KEYWORDS = ["id", "date", "type", "code"]

    if any(k in column_text for k in NEGATIVE_KEYWORDS):
        score -= 0.5
        reasons.append("column name suggests identifier or metadata")

    # ── Frequency inference ───────────────────────────────────

    if any(k in column_text for k in WEEK_KEYWORDS):
        frequency = "Week"
        reasons.append("frequency inferred as Week")
    elif any(k in column_text for k in MONTH_KEYWORDS):
        frequency = "Month"
        reasons.append("frequency inferred as Month")
    elif any(k in column_text for k in TOTAL_KEYWORDS):
        frequency = "Total"
        reasons.append("frequency inferred as Total")
    else:
        frequency = None
        reasons.append("frequency unclear")

    # ── Context inference ─────────────────────────────────────

    if any(k in column_text for k in NET_KEYWORDS):
        context = "net"
        reasons.append("context inferred as net")
    elif any(k in column_text for k in GROSS_KEYWORDS):
        context = "gross"
        reasons.append("context inferred as gross")
    else:
        context = None
        reasons.append("context unclear")

    # ── Final decision ────────────────────────────────────────

    is_amount = score >= 0.6

    return {
        "source_file": source_file,
        "source_field": column_name,
        "target_concept": "MonetaryAmount" if is_amount else None,
        "currency": currency if is_amount else None,
        "frequency": frequency if is_amount else None,
        "context": context if is_amount else None,
        "confidence": round(max(score, 0.0), 2),
        "reason": "; ".join(reasons),
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


def print_results(results: list[dict[str, Any]]) -> None:
    print("=" * 64)
    print("Amount mapping reasoner")
    print("=" * 64)

    for result in results:
        print()
        print(f"Column:     {result['source_field']}")
        print(f"Concept:    {result['target_concept']}")
        print(f"Confidence: {result['confidence']}")
        print(f"Currency:   {result['currency']}")
        print(f"Frequency:  {result['frequency']}")
        print(f"Context:    {result['context']}")
        print(f"Reason:     {result['reason']}")


if __name__ == "__main__":
    results = run_reasoner_on_csv(DEFAULT_FILE)
    print_results(results)