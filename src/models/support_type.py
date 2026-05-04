"""
Target schema for the SupportType concept.

A SupportType is the unified representation of the type of support, benefit,
grant, loan, or financial assistance described by a source authority.

Source datasets express support types differently:

  • AF uses benefit_type to describe support such as "Activity support".
  • FK uses benefit_type and benefit_group_code to describe benefit categories.
  • CSN uses support_type, support_form_code, amount_type_code, and grant_code
    to describe study-support related support types such as grants and loans.

The model explicitly captures:

  • support_type — the ontology-level support category.

  • source_value — the original value found in the CSV, such as
    "Activity support", "FK:AS", "student_grant", "GRUNDB", or "GRUNDL".

  • source_description — optional human-readable explanation from the source,
    such as support_form_description or amount_type_label.

  • provenance (source_file + source_field + source_record_id) — every
    SupportType instance can be traced back to the exact row and field it came
    from. This lets the demo show *why* a support type was created.

Mirrors the ontology's :SupportType concept with provenance metadata and
source-level explanation fields needed for reliable transformation and
explainability.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SupportTypeValue(str, Enum):
    ACTIVITY_SUPPORT = "ActivitySupport"
    STUDENT_GRANT = "StudyGrant"
    STUDENT_LOAN = "StudyLoan"
    STUDY_SUPPORT = "StudySupport"


class SupportType(BaseModel):
    support_type: SupportTypeValue = Field(...)
    source_value: str
    source_description: Optional[str] = None

    # provenance
    source_file: str
    source_field: str
    source_record_id: str

    def __str__(self) -> str:
        return self.support_type.value