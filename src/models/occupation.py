"""
Target schema for the Occupation concept.

An Occupation is the unified representation of a person's role/status as
understood by the ontology. In the current ontology, the valid occupation
types are:

  • Employer
  • Job seeker
  • Student

Source datasets express these roles differently. AF data identifies job
seekers through job seeker status/category fields. CSN data identifies
students through study support cases, grant decisions, study mode, or study
pace. Employer is included because the ontology allows it, even if the current
source CSVs may not always provide employer-specific records.

The model explicitly captures:

  • occupation_type — the ontology-level occupation category.

  • source_value — the original value found in the CSV, such as
    "Openly unemployed", "student_grant", or another source-specific label.

  • scope_pct — optional percentage describing extent, such as study pace,
    job-seeking scope, or activity/support scope when provided.

  • provenance — every Occupation instance can be traced back to the exact
    row and field it came from. This lets the demo show why a person was
    classified as student, job seeker, or employer.

Mirrors the ontology's :Occupation concept with provenance metadata and
source-level explanation fields needed for reliable transformation and
explainability.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class OccupationType(str, Enum):
    """Occupation categories defined by the ontology."""

    EMPLOYER = "Employer"
    JOB_SEEKER = "JobSeeker"
    STUDENT = "Student"


class Occupation(BaseModel):
    """A unified occupation/status classification with provenance."""

    occupation_type: OccupationType = Field(
        ...,
        description="Ontology-level occupation category",
    )

    source_value: str = Field(
        ...,
        description="Original source value used to infer the occupation",
    )

    source_description: Optional[str] = Field(
        default=None,
        description="Optional human-readable explanation from the source",
    )

    scope_pct: Optional[int] = Field(
        default=None,
        description="Optional extent of the occupation/status, expressed as a percentage",
    )

    # Provenance
    source_file: str
    source_field: str = Field(
        ...,
        description="Original CSV field used to infer the occupation",
    )
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row",
    )

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
            raise ValueError("Required Occupation source/provenance values cannot be empty")
        return value

    @field_validator("scope_pct")
    @classmethod
    def scope_must_be_percentage(cls, value: Optional[int]) -> Optional[int]:
        if value is not None and not 0 <= value <= 100:
            raise ValueError("Occupation.scope_pct must be between 0 and 100")
        return value

    def __str__(self) -> str:
        if self.scope_pct is None:
            return self.occupation_type.value
        return f"{self.occupation_type.value} ({self.scope_pct}%)"


def demo_model() -> None:
    print("=" * 64)
    print("Occupation Pydantic model")
    print("=" * 64)
    print()

    print("This model defines the required backend structure for Occupation.")
    print("It ensures that each output has:")
    print("  - one ontology-level occupation category")
    print("  - the original source value")
    print("  - optional source description")
    print("  - optional scope percentage")
    print("  - provenance back to file, field, and row")
    print()

    print("Allowed enum values:")
    for value in OccupationType:
        print(f"  - {value.value}")

    print()
    print("Example validated instance:")
    print()

    example = Occupation(
        occupation_type=OccupationType.STUDENT,
        source_value="student_grant",
        source_description="CSN study support case indicating student status",
        scope_pct=100,
        source_file="csn_grant_decision.csv",
        source_field="decision_type",
        source_record_id="row0",
    )

    print(example.model_dump_json(indent=2))


if __name__ == "__main__":
    demo_model()