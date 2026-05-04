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

Source datasets express status differently. AF may describe whether a person
is currently registered or whether a decision is active/inactive. CSN may
describe study-support decisions as approved, planned, or initiated. FK may
describe cases, decisions, or payments through administrative lifecycle fields.

The model explicitly captures:

  • status_type — the ontology-level lifecycle state.

  • source_value — the original value found in the CSV, such as
    "approved", "active", "false", "submitted", or another source-specific
    label.

  • source_description — optional human-readable context from the source,
    when available.

  • provenance (source_file + source_field + source_record_id) — every
    Status instance can be traced back to the exact row and field it came
    from. This lets the demo show *why* an Income record was classified as
    active, approved, inactive, initiated, or planned.

Mirrors the ontology's :Status concept with provenance metadata and
source-level explanation fields needed for reliable transformation and
explainability.
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

    # Provenance — required so every Status can be traced
    source_file: str
    source_field: str = Field(
        ...,
        description="Original CSV field used to infer the status",
    )
    source_record_id: str = Field(
        ...,
        description="Stable identifier for the originating row "
                    "(row index or a composite of join keys)",
    )

    def __str__(self) -> str:
        return self.status_type.value