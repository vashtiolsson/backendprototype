from __future__ import annotations

import json
import os
from typing import Any

from openai import OpenAI


client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


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
    Real LLM-backed fallback suggester for SupportType mappings.

    The LLM only suggests candidate ontology values.
    Human review is still required before transformation.
    """

    prompt = f"""
You are helping map source-system support values to ontology values.

Allowed ontology values:
- ActivitySupport
- StudyGrant
- StudyLoan
- UnknownNeedsReview

Source file:
{source_file}

Source field:
{source_field}

Unknown source value:
{source_value}

Sample values from the same field:
{sample_values}

Reasoner rationale:
{rationale}

Return ONLY valid JSON:

{{
  "suggested_target_value": "...",
  "confidence": 0.0,
  "explanation": "..."
}}
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful ontology mapping assistant. "
                        "Return JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
        )

        content = response.choices[0].message.content or "{}"

        parsed = json.loads(content)

        suggested_value = parsed.get(
            "suggested_target_value",
            "UnknownNeedsReview",
        )

        if suggested_value not in ALLOWED_SUPPORT_TYPE_VALUES:
            suggested_value = "UnknownNeedsReview"

        return {
            "source_value": source_value,
            "suggested_target_value": suggested_value,
            "confidence": parsed.get("confidence", 0.0),
            "needs_human_review": True,
            "approved": False,
            "method": "llm_fallback_suggester_openai",
            "allowed_values": sorted(ALLOWED_SUPPORT_TYPE_VALUES),
            "explanation": parsed.get("explanation", ""),
            "sample_values_seen": sample_values[:10],
        }

    except Exception as error:
        return {
            "source_value": source_value,
            "suggested_target_value": "UnknownNeedsReview",
            "confidence": 0.0,
            "needs_human_review": True,
            "approved": False,
            "method": "llm_fallback_error",
            "allowed_values": sorted(ALLOWED_SUPPORT_TYPE_VALUES),
            "explanation": f"LLM fallback failed: {error}",
            "sample_values_seen": sample_values[:10],
        }