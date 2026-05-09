"""
Target schema for the TimePeriod concept.

A TimePeriod is the unified representation of any bounded time interval
arriving from a source CSV. It explicitly captures three things that
the source data leaves implicit:

  • start_date and end_date — required by the ontology's :TimePeriod
    concept. Source datasets express periods differently: AF and FK use
    ordinary dates, while CSN may use compact dates or ISO year-week values.

  • source format — important because dates may arrive as YYYY-MM-DD,
    YYYYMMDD, or YYYYWW. Without an explicit source format, the system
    cannot safely normalize periods across authorities.

  • provenance — every instance can be traced back to the exact row and
    fields it came from. This lets the demo show why a period appeared.

Mirrors the ontology's :TimePeriod class with the addition of source_format
and provenance metadata, which are implementation details needed for reliable
transformation and explanation.
"""

from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TimeFormat(str, Enum):
    """Supported source date/week formats found in the synthetic datasets."""

    DATE = "Date"
    COMPACT_DATE = "CompactDate"
    YEAR_WEEK = "YearWeek"


class Period(BaseModel):
    """A unified time interval with explicit semantics and provenance."""

    start_date: date = Field(
        ...,
        description="First day of the period",
    )

    end_date: Optional[date] = Field(
        default=None,
        description="Last day of the period; None means open-ended or unavailable",
    )

    source_format: TimeFormat = Field(
        ...,
        description="Original source format before normalization",
    )

    source_start_value: str = Field(
        ...,
        description="Original source value used to create the start date",
    )

    source_end_value: Optional[str] = Field(
        default=None,
        description="Original source value used to create the end date",
    )

    source_description: Optional[str] = Field(
        default=None,
        description="Optional human-readable explanation from the source",
    )

    # Provenance
    source_file: str
    source_start_field: str = Field(
        ...,
        description="Original CSV field used to infer the start date",
    )
    source_end_field: Optional[str] = Field(
        default=None,
        description="Original CSV field used to infer the end date",
    )
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row",
    )

    @field_validator(
        "source_start_value",
        "source_file",
        "source_start_field",
        "source_record_id",
    )
    @classmethod
    def required_text_values_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Required TimePeriod source/provenance values cannot be empty")
        return value

    @model_validator(mode="after")
    def end_must_not_be_before_start(self) -> "Period":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("Period.end_date cannot be before start_date")
        return self

    def __str__(self) -> str:
        if self.end_date is None:
            return f"{self.start_date.isoformat()} → open-ended"
        return f"{self.start_date.isoformat()} → {self.end_date.isoformat()}"


def demo_model() -> None:
    print("=" * 64)
    print("Period Pydantic model")
    print("=" * 64)
    print()

    print("This model defines the required backend structure for Period.")
    print("It ensures that each output has:")
    print("  - a normalized start date")
    print("  - an optional normalized end date")
    print("  - the original source format")
    print("  - the original source values")
    print("  - optional source description")
    print("  - provenance back to file, fields, and row")
    print()

    print("Allowed enum values:")
    for value in TimeFormat:
        print(f"  - {value.value}")

    print()
    print("Example validated instance:")
    print()

    example = Period(
        start_date=date(2025, 9, 1),
        end_date=date(2025, 12, 31),
        source_format=TimeFormat.DATE,
        source_start_value="2025-09-01",
        source_end_value="2025-12-31",
        source_description="AF activity period for a registered support case",
        source_file="af_activity_report.csv",
        source_start_field="start_date",
        source_end_field="end_date",
        source_record_id="row0",
    )

    print(example.model_dump_json(indent=2))


if __name__ == "__main__":
    demo_model()