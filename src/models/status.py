"""
Target schema for the Status concept.

A Status is the unified representation of the lifecycle state of an Income
record in the source authority's system. According to the ontology, the valid
status values are:

  • Active
  • Approved
  • Inactive
  • Initiated
  • Planned
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class StatusType(str, Enum):
    """Lifecycle states defined by the ontology."""

    ACTIVE = "Active"
    APPROVED = "Approved"
    INACTIVE = "Inactive"
    INITIATED = "Initiated"
    PLANNED = "Planned"


class Status(BaseModel):
    """A unified income lifecycle status with provenance."""

    status_type: StatusType = Field(
        ...,
        description="Ontology-level lifecycle status",
    )

    source_value: str = Field(
        ...,
        description="Original source value used to infer the status",
    )

    source_description: Optional[str] = Field(
        default=None,
        description="Optional human-readable explanation from the source",
    )

    # Provenance
    source_file: str
    source_field: str = Field(
        ...,
        description="Original CSV field used to infer the status",
    )
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row",
    )

    def __str__(self) -> str:
        return self.status_type.value


def demo_model() -> None:
    print("=" * 64)
    print("Status Pydantic model")
    print("=" * 64)
    print()

    print("This model defines the required backend structure for Status.")
    print("It ensures that each output has:")
    print("  - one ontology-level status")
    print("  - the original source value")
    print("  - optional source description")
    print("  - provenance back to file, field, and row")
    print()

    print("Allowed enum values:")
    for value in StatusType:
        print(f"  - {value.value}")

    print()
    print("Example validated instance:")
    print()

    example = Status(
        status_type=StatusType.APPROVED,
        source_value="approved",
        source_description="CSN approved status",
        source_file="csn_grant_decision.csv",
        source_field="status",
        source_record_id="row0",
    )

    print(example.model_dump_json(indent=2))


if __name__ == "__main__":
    demo_model()