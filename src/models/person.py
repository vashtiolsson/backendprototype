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

from pydantic import BaseModel, Field, field_validator


class Person(BaseModel):
    """A unified person identity shared across authority datasets."""

    person_id: str = Field(
        ...,
        description="Stable person identifier used to link records across AF, FK, and CSN",
    )

    @field_validator("person_id")
    @classmethod
    def person_id_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Person.person_id cannot be empty")
        return value

    def __str__(self) -> str:
        return self.person_id