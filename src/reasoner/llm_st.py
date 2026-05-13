from __future__ import annotations

from typing import Any


ALLOWED_SUPPORT_TYPE_VALUES = {
    "ActivitySupport",
    "StudyGrant",
    "StudyLoan",
    "UnknownNeedsReview",
}


def suggest_support_type_mapping(
    source_file: str,
    source_field: str,
    source_value: str,
    sample_values: list[str],
    rationale: str,
) -> dict[str, Any]:
    """
    LLM-style fallback suggester for SupportType mappings.

    In the thesis prototype, this simulates what an LLM would do:
    suggest a likely ontology value for an unmapped source value.

    Important:
    - It does NOT approve mappings automatically.
    - It only returns a candidate.
    - The suggestion must still be reviewed by a human.
    """

    normalized_value = source_value.strip().lower()

    explanation_parts = [
        f"Source value '{source_value}' appeared in field '{source_field}' from file '{source_file}'.",
        f"The reasoner rationale was: {rationale}",
    ]

    if normalized_value in {"as", "fk:as", "activity support", "activity_support"}:
        suggested_value = "ActivitySupport"
        confidence = 0.85
        explanation_parts.append(
            "The value looks like an abbreviation or label for activity support."
        )

    elif normalized_value in {"grundb", "grant", "study grant", "student_grant", "study_grant"}:
        suggested_value = "StudyGrant"
        confidence = 0.85
        explanation_parts.append(
            "The value appears to refer to a grant-type study support."
        )

    elif normalized_value in {"grundl", "loan", "study loan", "student_loan", "study_loan"}:
        suggested_value = "StudyLoan"
        confidence = 0.85
        explanation_parts.append(
            "The value appears to refer to a loan-type study support."
        )

    else:
        suggested_value = "UnknownNeedsReview"
        confidence = 0.35
        explanation_parts.append(
            "The value could not be safely mapped to a known ontology value."
        )

    if suggested_value not in ALLOWED_SUPPORT_TYPE_VALUES:
        suggested_value = "UnknownNeedsReview"
        confidence = 0.0

    return {
        "source_value": source_value,
        "suggested_target_value": suggested_value,
        "confidence": confidence,
        "needs_human_review": True,
        "approved": False,
        "method": "llm_fallback_suggester_simulated",
        "allowed_values": sorted(ALLOWED_SUPPORT_TYPE_VALUES),
        "explanation": " ".join(explanation_parts),
        "sample_values_seen": sample_values[:10],
    }