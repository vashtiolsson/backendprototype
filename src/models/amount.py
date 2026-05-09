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

  • provenance — every instance can be traced back to the exact row and
    field it came from. This lets the demo show why a number appeared.

Mirrors the ontology's :MonetaryAmount class with the addition of context
and provenance metadata needed for reliable transformation and explanation.
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Frequency(str, Enum):
    """Frequency categories defined by the ontology."""

    WEEK = "Week"
    MONTH = "Month"
    TOTAL = "Total"


class ValueContext(str, Enum):
    """Whether the amount is before tax or after tax."""

    GROSS = "gross"
    NET = "net"


class MonetaryAmount(BaseModel):
    """A unified monetary value with explicit semantics and provenance."""

    value: Decimal = Field(
        ...,
        description="Numeric monetary amount",
    )

    currency: str = Field(
        default="SEK",
        description="ISO 4217 currency code",
    )

    frequency: Frequency = Field(
        ...,
        description="Whether the amount is per week, per month, or a total",
    )

    context: Optional[ValueContext] = Field(
        default=None,
        description="Gross/net distinction; None means unspecified",
    )

    source_value: str = Field(
        ...,
        description="Original source value used to create the monetary amount",
    )

    source_description: Optional[str] = Field(
        default=None,
        description="Optional human-readable explanation from the source",
    )

    # Provenance
    source_file: str
    source_field: str = Field(
        ...,
        description="Original CSV field used to infer the monetary amount",
    )
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row",
    )

    @field_validator("value")
    @classmethod
    def value_must_be_non_negative(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("MonetaryAmount.value cannot be negative")
        return value

    @field_validator("currency")
    @classmethod
    def currency_must_be_valid_code(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 3:
            raise ValueError("MonetaryAmount.currency must be a 3-letter ISO code")
        return value

    @field_validator(
        "source_value",
        "source_file",
        "source_field",
        "source_record_id",
    )
    @classmethod
    def required_text_values_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Required MonetaryAmount source/provenance values cannot be empty")
        return value

    def __str__(self) -> str:
        context = f" {self.context.value}" if self.context else ""
        return f"{self.value:,.0f} {self.currency}/{self.frequency.value}{context}"


def demo_model() -> None:
    print("=" * 64)
    print("MonetaryAmount Pydantic model")
    print("=" * 64)
    print()

    print("This model defines the required backend structure for MonetaryAmount.")
    print("It ensures that each output has:")
    print("  - one numeric monetary value")
    print("  - a currency")
    print("  - one frequency")
    print("  - optional gross/net context")
    print("  - the original source value")
    print("  - optional source description")
    print("  - provenance back to file, field, and row")
    print()

    print("Allowed frequency values:")
    for value in Frequency:
        print(f"  - {value.value}")

    print()
    print("Allowed context values:")
    for value in ValueContext:
        print(f"  - {value.value}")

    print()
    print("Example validated instance:")
    print()

    example = MonetaryAmount(
        value=Decimal("12500"),
        currency="SEK",
        frequency=Frequency.MONTH,
        context=ValueContext.NET,
        source_value="12500",
        source_description="FK monthly net payment after tax withholding",
        source_file="fk_payment.csv",
        source_field="net_sek",
        source_record_id="row0",
    )

    print(example.model_dump_json(indent=2))


if __name__ == "__main__":
    demo_model()