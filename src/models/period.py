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

  • provenance (source_file + source_start_field + source_end_field
    + source_record_id) — every instance can be traced back to the exact
    row and fields it came from. This lets the demo show *why* a period
    appeared.

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

    DATE = "Date"              # YYYY-MM-DD
    COMPACT_DATE = "CompactDate"  # YYYYMMDD
    YEAR_WEEK = "YearWeek"     # YYYYWW


class TimePeriod(BaseModel):
    """A unified time interval with explicit semantics and provenance."""

    start_date: date = Field(..., description="First day of the period")
    end_date: Optional[date] = Field(
        default=None,
        description="Last day of the period; None means open-ended or unavailable",
    )
    source_format: TimeFormat = Field(
        ...,
        description="Original source format before normalization",
    )

    # Provenance — required so every TimePeriod can be traced
    source_file: str
    source_start_field: str
    source_end_field: Optional[str] = Field(
        default=None,
        description="Original end-date field; None if the source has no end field",
    )
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row "
                    "(row index or a composite of join keys)",
    )

    @model_validator(mode="after")
    def end_must_not_be_before_start(self) -> "TimePeriod":
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("TimePeriod.end_date cannot be before start_date")
        return self

    def __str__(self) -> str:
        if self.end_date is None:
            return f"{self.start_date.isoformat()} → open-ended"
        return f"{self.start_date.isoformat()} → {self.end_date.isoformat()}"