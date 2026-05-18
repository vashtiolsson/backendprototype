"""
Target schema for the SupportType concept.

A SupportType is the unified representation of the type of support, benefit,
grant, loan, or financial assistance described by a source authority.

Different authorities express support types differently:

  - AF may use benefit_type, such as "Activity support".
  - FK may use benefit_group_code, such as "FK:AS".
  - CSN may use support_type, support_form_code, decision_type,
    or amount_type_code, such as "GRUNDB" or "GRUNDL".

This model stores:
  1. the concrete ontology-level support type,
  2. the broader ontology support group,
  3. provenance showing where the interpretation came from, and
  4. mapping trace information showing which rule created the interpretation.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SupportTypeValue(str, Enum):
    """Allowed concrete ontology-level support type individuals."""

    ACTIVITY_SUPPORT = "ActivitySupport"
    STUDY_GRANT = "StudyGrant"
    STUDY_LOAN = "StudyLoan"


class SupportGroupValue(str, Enum):
    """Allowed broader ontology-level support groups."""

    STUDY_SUPPORT = "StudySupport"
    WORK_SUPPORT = "WorkSupport"


class SupportType(BaseModel):
    """Ontology-aligned support type with source provenance and mapping trace."""

    model_config = ConfigDict(extra="forbid")

    support_type: SupportTypeValue = Field(
        ...,
        description="Concrete ontology-level support type",
    )

    support_group: SupportGroupValue = Field(
        ...,
        description="Broader ontology class, such as StudySupport or WorkSupport",
    )

    source_value: str = Field(
        ...,
        description="Original source value used to infer the support type",
    )

    source_description: Optional[str] = Field(
        default=None,
        description="Optional human-readable source description",
    )

    # Provenance
    source_file: str = Field(
        ...,
        description="Source CSV file",
    )

    source_field: str = Field(
        ...,
        description="Source CSV field",
    )

    source_record_id: str = Field(
        ...,
        description="Stable row identifier in the source file",
    )

    # Mapping trace
    mapping_rule_id: str = Field(
        ...,
        description="ID of the approved mapping rule that created this object",
    )

    mapping_rationale: Optional[str] = Field(
        default=None,
        description="Human-readable rationale from the approved mapping rule",
    )

    @field_validator(
        "source_value",
        "source_file",
        "source_field",
        "source_record_id",
        "mapping_rule_id",
    )
    @classmethod
    def required_text_must_not_be_empty(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Required SupportType provenance values cannot be empty")

        return value

    @model_validator(mode="after")
    def support_type_must_match_support_group(self) -> "SupportType":
        expected_groups = {
            SupportTypeValue.STUDY_GRANT: SupportGroupValue.STUDY_SUPPORT,
            SupportTypeValue.STUDY_LOAN: SupportGroupValue.STUDY_SUPPORT,
            SupportTypeValue.ACTIVITY_SUPPORT: SupportGroupValue.WORK_SUPPORT,
        }

        expected_group = expected_groups[self.support_type]

        if self.support_group != expected_group:
            raise ValueError(
                f"{self.support_type.value} must belong to {expected_group.value}, "
                f"not {self.support_group.value}"
            )

        return self

    def __str__(self) -> str:
        return self.support_type.value


def demo_model() -> None:
    print("=" * 64)
    print("SupportType Pydantic model")
    print("=" * 64)
    print()

    example = SupportType(
        support_type=SupportTypeValue.STUDY_GRANT,
        support_group=SupportGroupValue.STUDY_SUPPORT,
        source_value="GRUNDB",
        source_description="Grant",
        source_file="csn_approved_amounts.csv",
        source_field="amount_type_code",
        source_record_id="row0",
        mapping_rule_id="support.csn.approved_amounts.amount_type_code",
        mapping_rationale="GRUNDB represents the grant component and maps to StudyGrant.",
    )

    print(example.model_dump_json(indent=2))


if __name__ == "__main__":
    demo_model()