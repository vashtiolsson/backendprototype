"""
Target schema for the Amount concept.

A MonetaryAmount is the unified representation of any monetary value
arriving from a source CSV. It explicitly captures three things that
the source data leaves implicit:

  • frequency (Week / Month / Total) — required, because CSN denominates
    per week, FK per month, and both also expose totals; without an
    explicit frequency you cannot safely add them.

  • context (gross / net) — important for FK where both are present;
    for CSN we store gross because there is no tax withholding on
    student finance.

  • provenance (source_file + source_field + source_record_id) — every
    instance can be traced back to the exact row it came from. This
    is what lets the demo show *why* a number appeared.

Mirrors the ontology's :MonetaryAmount class with the addition of
context (which the ontology does not yet model — worth adding later).
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Frequency(str, Enum):
    """Mirrors :Frequency individuals in the ontology."""
    WEEK  = "Week"
    MONTH = "Month"
    TOTAL = "Total"


class ValueContext(str, Enum):
    """Whether the amount is before tax (gross) or after (net).

    Not yet in the ontology — proposed extension. CSN amounts are gross
    by convention (no withholding); FK exposes both for Aktivitetsstöd.
    """
    GROSS = "gross"
    NET   = "net"


class MonetaryAmount(BaseModel):
    """A unified monetary value with explicit semantics and provenance."""

    value:     Decimal       = Field(..., description="Numeric amount")
    currency:  str           = Field(default="SEK", description="ISO 4217 code")
    frequency: Frequency     = Field(..., description="Per week / month / total")
    context:   Optional[ValueContext] = Field(
        default=None,
        description="gross/net distinction (None = unspecified)",
    )

    # Provenance — required so every Amount can be traced
    source_file:      str
    source_field:     str
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row "
                    "(row index or a composite of join keys)",
    )

    @field_validator("value")
    @classmethod
    def value_must_be_non_negative(cls, v: Decimal) -> Decimal:
        if v < 0:
            raise ValueError("MonetaryAmount.value cannot be negative")
        return v

    def __str__(self) -> str:
        ctx = f" {self.context.value}" if self.context else ""
        return f"{self.value:,.0f} {self.currency}/{self.frequency.value}{ctx}"