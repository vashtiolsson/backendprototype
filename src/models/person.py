"""
Target schema for the Person concept.

A Person is the unified representation of an individual appearing across
the source CSV files.

In the synthetic SSBTEK data, all authorities identify people using the
same shared field:

  • personal_id — Swedish personal identity number, used as the join key
    across AF, FK, and CSN source files.

The ontology's :Person concept only requires a person identifier. Other
attributes, such as name, job-seeker status, student status, benefit cases,
payments, or study periods, belong to source-specific records or related
ontology concepts — not directly to Person.

This model therefore keeps Person intentionally minimal. It exists to make
cross-authority linking explicit without adding implementation-specific or
source-only attributes.
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class Person(BaseModel):
    """A unified person identity shared across authority datasets with provenance."""

    person_id: str = Field(
        ...,
        description="Stable person identifier used to link records across AF, FK, and CSN",
    )

    source_value: str = Field(
        ...,
        description="Original source value used to create the person identity",
    )

    source_description: Optional[str] = Field(
        default=None,
        description="Optional human-readable explanation from the source",
    )

    # Provenance
    source_file: str
    source_field: str = Field(
        ...,
        description="Original CSV field used to identify the person",
    )
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row",
    )

    @field_validator("person_id", "source_value")
    @classmethod
    def values_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Person identifiers cannot be empty")
        return value

    def __str__(self) -> str:
        return self.person_id


def demo_model() -> None:
    print("=" * 64)
    print("Person Pydantic model")
    print("=" * 64)
    print()

    print("This model defines the required backend structure for Person.")
    print("It ensures that each output has:")
    print("  - a stable person identifier")
    print("  - the original source value")
    print("  - optional source description")
    print("  - provenance back to file, field, and row")
    print()

    print("Example validated instance:")
    print()

    example = Person(
        person_id="20000421-1234",
        source_value="20000421-1234",
        source_description="Shared personal identity number used across AF, FK, and CSN",
        source_file="csn_grant_decision.csv",
        source_field="personal_id",
        source_record_id="row0",
    )

    print(example.model_dump_json(indent=2))


if __name__ == "__main__":
    demo_model()