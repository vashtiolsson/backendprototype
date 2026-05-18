"""
Reasoner for the SupportType concept.

Purpose
-------
The reasoner scans CSV files and decides which columns are likely to carry
SupportType source values. The matcher and transformer should only receive
fields that are classified as primary mapping fields.

This version improves the previous calibrated reasoner by adding:

1. A stricter acceptance threshold.
2. A lower score for broad/contextual fields such as support_form_code.
3. Explicit field roles:
      - primary_mapping_field: can be sent to matcher/transformer
      - review_field: possible candidate, but not auto-sent
      - descriptor_field: human-readable label/description for another field
      - context_field: useful context, but not the final SupportType source
      - evidence_field: supporting evidence, but not the final mapping field
      - rejected_field: clearly not a SupportType source-value field
4. Clear terminal output when the reasoner is run directly.

Run from project root:
    python3 -m src.new.reasoner_st

Or directly:
    python3 src/new/reasoner_st.py
"""

from __future__ import annotations

import csv
import math
import re
import statistics
from pathlib import Path
from typing import Any, Optional

from src.new.model_st import (
    SupportGroupValue,
    SupportType,
    SupportTypeValue,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"

# A stricter threshold than 0.55. The reasoner controls what enters the
# matcher/transformer, so weak matches should be reviewed rather than accepted.
ACCEPTANCE_THRESHOLD = 0.65

PERSON_ID_FIELDS = ("personal_id", "person_id", "pnr")


# ---------------------------------------------------------------------------
# Model-driven target rules
# ---------------------------------------------------------------------------

TARGET_CONCEPT = SupportType.__name__
SUPPORT_TYPE_MODEL_FIELDS = set(SupportType.model_fields.keys())

SUPPORT_TYPE_TARGET_FIELD = "support_type"
SUPPORT_GROUP_TARGET_FIELD = "support_group"
SOURCE_VALUE_MODEL_FIELD = "source_value"

PROVENANCE_MODEL_FIELDS = {
    "source_value",
    "source_description",
    "source_file",
    "source_field",
    "source_record_id",
}

MAPPING_TRACE_MODEL_FIELDS = {
    "mapping_rule_id",
    "mapping_rationale",
}

ALLOWED_SUPPORT_TYPES = {item.value for item in SupportTypeValue}
ALLOWED_SUPPORT_GROUPS = {item.value for item in SupportGroupValue}


# ---------------------------------------------------------------------------
# Source-side detection vocabulary
# ---------------------------------------------------------------------------
# Specificity is a signal, not a final decision. A field can score highly but
# still be classified as context/evidence if its semantic role is too broad.

SUPPORT_TYPE_NAME_PATTERNS: list[tuple[str, float]] = [
    ("support_type", 0.95),
    ("benefit_type", 0.85),
    ("benefit_group_code", 0.85),
    ("amount_type_code", 0.85),
    ("grant_code", 0.80),

    # Lowered deliberately: support_form_code often describes a broader form
    # such as GRUND, not the exact ontology value StudyGrant/StudyLoan.
    ("support_form_code", 0.55),

    ("benefit_group", 0.65),
    ("amount_type", 0.60),
    ("support_form", 0.50),
    ("decision_type", 0.45),
]

# Fields that are allowed to become primary mapping fields when confidence is
# high enough. These are the fields that can safely feed the matcher.
PRIMARY_SOURCE_FIELD_NAMES = {
    "support_type",
    "benefit_type",
    "benefit_group_code",
    "amount_type_code",
    "grant_code",
}

# Fields that may be useful, but should not be treated as the final source
# value for the SupportType object.
CONTEXT_EXACT_FIELDS = {
    "support_form_code",
    "support_form",
    "loan_applied",
    "grant_applied",
    "application_type",
    "measure_code",
    "measure_description",
}

EVIDENCE_EXACT_FIELDS = {
    "decision_type",
    "decision_status",
    "case_status",
    "status",
}

# Columns that are almost never the main source-value field. Strong negative.
NEGATIVE_EXACT_FIELDS = {
    "personal_id", "person_id", "pnr",
    "case_id", "decision_id", "payment_id", "period_id", "activity_id",
    "date", "start_date", "end_date", "week", "month",
    "amount", "amount_sek", "total_amount", "total_amount_sek",
    "gross_amount_sek", "net_amount_sek", "tax_withheld_sek",
    "currency", "sek", "pct", "scope",
}

DESCRIPTION_OR_LABEL_KEYWORDS = ("description", "label", "text", "name")

KNOWN_SUPPORT_SOURCE_VALUES = {
    "activity support", "activitysupport", "fk:as", "as",
    "student_grant", "study_grant", "student_loan", "study_loan",
    "studygrant", "studyloan", "grant", "loan",
    "grund", "grundb", "grundl",
}

SOURCE_VALUE_TO_SUPPORT_TYPE = {
    # Work support
    "activity support": "ActivitySupport",
    "activitysupport": "ActivitySupport",
    "fk:as": "ActivitySupport",

    # Study support
    "student_grant": "StudyGrant",
    "study_grant": "StudyGrant",
    "studygrant": "StudyGrant",
    "grant": "StudyGrant",
    "grundb": "StudyGrant",

    "student_loan": "StudyLoan",
    "study_loan": "StudyLoan",
    "studyloan": "StudyLoan",
    "loan": "StudyLoan",
    "grundl": "StudyLoan",

    # Keep GRUND broad. It should not auto-map.
    "grund": "UnknownNeedsReview",
}

SUPPORT_TYPE_TO_GROUP = {
    "ActivitySupport": "WorkSupport",
    "StudyGrant": "StudySupport",
    "StudyLoan": "StudySupport",
}

NUMERIC_VALUE_RE = re.compile(r"^-?\d+([.,]\d+)?$")
DATE_VALUE_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}")


# ---------------------------------------------------------------------------
# Calibrated logistic combiner
# ---------------------------------------------------------------------------

SIGNAL_WEIGHTS = {
    "intercept": -3.0,

    # Positive signals
    "name_exact_target_field": 4.0,
    "name_pattern_specificity": 4.2,
    "value_target_match": 3.8,
    "value_source_hint_match": 3.4,
    "description_sibling_present": 0.6,
    "low_cardinality_categorical": 0.8,

    # Negative signals
    "name_in_negative_list": -5.0,
    "is_description_column": -2.0,
    "values_look_numeric": -3.0,
    "values_look_like_dates": -3.0,
    "values_freeform_high_cardinality": -1.5,
}


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


# ---------------------------------------------------------------------------
# Signal extractors
# ---------------------------------------------------------------------------

def _normalize_text(value: Any) -> str:
    return str(value).strip().lower()


def _is_description_column_name(column_name: str) -> bool:
    lower = column_name.lower()
    return any(keyword in lower for keyword in DESCRIPTION_OR_LABEL_KEYWORDS)


def _name_signals(column_name: str) -> dict[str, float]:
    lower = column_name.lower()

    exact = 1.0 if lower == SUPPORT_TYPE_TARGET_FIELD else 0.0

    best_specificity = 0.0
    for pattern, specificity in SUPPORT_TYPE_NAME_PATTERNS:
        if pattern in lower and specificity > best_specificity:
            best_specificity = specificity

    return {
        "name_exact_target_field": exact,
        "name_pattern_specificity": best_specificity,
        "name_in_negative_list": 1.0 if lower in NEGATIVE_EXACT_FIELDS else 0.0,
        "is_description_column": 1.0 if _is_description_column_name(column_name) else 0.0,
    }


def _value_signals(values: list[Any]) -> tuple[dict[str, float], dict[str, Any]]:
    cleaned = [
        _normalize_text(v)
        for v in values
        if v is not None and str(v).strip() != "" and _normalize_text(v) != "nan"
    ]
    checked = len(cleaned)

    if checked == 0:
        return (
            {
                "value_target_match": 0.0,
                "value_source_hint_match": 0.0,
                "low_cardinality_categorical": 0.0,
                "values_look_numeric": 0.0,
                "values_look_like_dates": 0.0,
                "values_freeform_high_cardinality": 0.0,
            },
            {
                "checked": 0,
                "unique": 0,
                "matched_target_values": [],
                "matched_source_hints": [],
                "numeric_share": 0.0,
                "date_share": 0.0,
                "mean_length": 0.0,
                "cardinality_ratio": 0.0,
            },
        )

    allowed_target_normalized = {_normalize_text(v) for v in ALLOWED_SUPPORT_TYPES}

    target_hits: list[str] = []
    hint_hits: list[str] = []
    numeric = 0
    dates = 0
    lengths: list[int] = []

    for text in cleaned:
        lengths.append(len(text))

        if NUMERIC_VALUE_RE.match(text):
            numeric += 1

        if DATE_VALUE_RE.match(text):
            dates += 1

        if text in allowed_target_normalized:
            target_hits.append(text)

        if text in KNOWN_SUPPORT_SOURCE_VALUES:
            hint_hits.append(text)

    unique_count = len(set(cleaned))
    cardinality_ratio = unique_count / checked
    mean_length = statistics.mean(lengths)

    low_card_signal = 0.0
    if cardinality_ratio <= 0.20 and mean_length <= 32:
        low_card_signal = 1.0
    elif cardinality_ratio <= 0.50:
        low_card_signal = 0.5

    target_share = len(target_hits) / checked
    hint_share = len(hint_hits) / checked
    numeric_share = numeric / checked
    date_share = dates / checked

    freeform = 0.0
    if cardinality_ratio >= 0.80 and mean_length >= 24:
        freeform = 1.0

    signals = {
        "value_target_match": min(target_share * 1.5, 1.0),
        "value_source_hint_match": min(hint_share * 1.5, 1.0),
        "low_cardinality_categorical": low_card_signal,
        "values_look_numeric": numeric_share,
        "values_look_like_dates": date_share,
        "values_freeform_high_cardinality": freeform,
    }

    diagnostics = {
        "checked": checked,
        "unique": unique_count,
        "matched_target_values": sorted(set(target_hits)),
        "matched_source_hints": sorted(set(hint_hits)),
        "numeric_share": round(numeric_share, 3),
        "date_share": round(date_share, 3),
        "mean_length": round(mean_length, 2),
        "cardinality_ratio": round(cardinality_ratio, 3),
    }

    return signals, diagnostics


def _description_sibling_signal(
    column_name: str,
    all_columns: list[str],
) -> tuple[float, Optional[str]]:
    description_field = _infer_description_field(column_name, all_columns)
    return (1.0 if description_field else 0.0, description_field)


def _infer_description_field(
    source_field: str,
    all_columns: list[str],
) -> Optional[str]:
    source_lower = source_field.lower()
    columns_by_lower = {column.lower(): column for column in all_columns}

    candidates: list[str] = []

    specific = {
        "amount_type_code": ["amount_type_label", "amount_type_description"],
        "support_form_code": ["support_form_description", "support_form_label"],
        "benefit_group_code": ["benefit_group_description", "benefit_group_label"],
        "grant_code": ["grant_description", "grant_label"],
        "benefit_type": ["benefit_type_description", "benefit_type_label"],
        "support_type": [
            "support_type_description",
            "support_type_label",
            "support_form_description",
        ],
    }
    candidates.extend(specific.get(source_lower, []))

    if source_lower.endswith("_code"):
        stem = source_lower.removesuffix("_code")
        candidates.extend(
            [f"{stem}_label", f"{stem}_description", f"{stem}_text", f"{stem}_name"]
        )

    if source_lower.endswith("_type"):
        candidates.extend([f"{source_lower}_label", f"{source_lower}_description"])

    for candidate in candidates:
        if candidate in columns_by_lower:
            return columns_by_lower[candidate]

    return None


# ---------------------------------------------------------------------------
# Field role classification
# ---------------------------------------------------------------------------

def _classify_field_role(
    column_name: str,
    confidence: float,
    name_signals: dict[str, float],
    value_signals: dict[str, float],
    value_diagnostics: dict[str, Any],
) -> tuple[str, str]:
    """
    Convert the statistical confidence into a semantic role.

    This is important because some fields can score high but still not be the
    right field to send to the transformer. Example: support_form_code=GRUND is
    useful context, but it is broader than StudyGrant/StudyLoan.
    """

    lower = column_name.lower()

    if name_signals["name_in_negative_list"]:
        return "rejected_field", "field name is known metadata or non-SupportType data"

    if value_signals["values_look_numeric"] >= 0.75:
        return "rejected_field", "values are mostly numeric, so this is unlikely to be a SupportType source value"

    if value_signals["values_look_like_dates"] >= 0.75:
        return "rejected_field", "values are mostly dates, so this is likely a period/date field"

    if value_signals["values_freeform_high_cardinality"]:
        return "rejected_field", "values look like freeform high-cardinality text"

    if _is_description_column_name(column_name):
        return "descriptor_field", "field looks like a label/description for another source field"

    if lower in CONTEXT_EXACT_FIELDS:
        return "context_field", "field is useful context, but too broad to be the final SupportType mapping field"

    if lower in EVIDENCE_EXACT_FIELDS:
        return "evidence_field", "field can support interpretation, but should not drive the final SupportType mapping"

    has_value_evidence = bool(
        value_diagnostics["matched_target_values"]
        or value_diagnostics["matched_source_hints"]
    )

    if (
        lower in PRIMARY_SOURCE_FIELD_NAMES
        and confidence >= ACCEPTANCE_THRESHOLD
        and has_value_evidence
    ):
        return (
            "primary_mapping_field",
            "field is a strong SupportType source-value candidate with known SupportType value evidence",
        )

    if confidence >= ACCEPTANCE_THRESHOLD and has_value_evidence:
        return "review_field", "field has strong evidence but is not in the approved primary field list"

    if name_signals["name_pattern_specificity"] > 0 or has_value_evidence:
        return "review_field", "field has some SupportType evidence but is not strong enough for automatic acceptance"

    return "rejected_field", "no strong SupportType evidence"


def _status_from_role(field_role: str) -> str:
    if field_role == "primary_mapping_field":
        return "accepted"
    if field_role in {"context_field", "evidence_field", "descriptor_field"}:
        return "context"
    if field_role == "review_field":
        return "review"
    return "rejected"


def _color_from_role(field_role: str) -> str:
    return {
        "primary_mapping_field": "teal",
        "review_field": "amber",
        "descriptor_field": "blue",
        "context_field": "slate",
        "evidence_field": "purple",
        "rejected_field": "gray",
    }.get(field_role, "gray")


# ---------------------------------------------------------------------------
# Combined scoring
# ---------------------------------------------------------------------------

def score_column(
    source_file: str,
    column_name: str,
    sample_values: list[Any],
    all_columns: list[str],
) -> dict[str, Any]:
    """
    Score one CSV column and classify its role.
    """

    name_signals = _name_signals(column_name)
    value_signals, value_diagnostics = _value_signals(sample_values)
    sibling_signal, description_field = _description_sibling_signal(
        column_name,
        all_columns,
    )

    signals = {
        **name_signals,
        **value_signals,
        "description_sibling_present": sibling_signal,
    }

    contributions: list[dict[str, Any]] = []
    log_odds = SIGNAL_WEIGHTS["intercept"]

    for signal_name, signal_value in signals.items():
        weight = SIGNAL_WEIGHTS.get(signal_name, 0.0)
        delta = weight * signal_value
        log_odds += delta

        contributions.append(
            {
                "signal": signal_name,
                "value": round(signal_value, 3),
                "weight": weight,
                "log_odds_delta": round(delta, 3),
                "polarity": "positive" if weight > 0 else "negative",
            }
        )

    contributions.sort(key=lambda c: abs(c["log_odds_delta"]), reverse=True)

    confidence = round(_sigmoid(log_odds), 3)

    field_role, role_reason = _classify_field_role(
        column_name=column_name,
        confidence=confidence,
        name_signals=name_signals,
        value_signals=value_signals,
        value_diagnostics=value_diagnostics,
    )

    is_main_source_value_field = field_role == "primary_mapping_field"

    rationale = _build_rationale(
        name_signals=name_signals,
        value_signals=value_signals,
        value_diagnostics=value_diagnostics,
        field_role=field_role,
        role_reason=role_reason,
    )

    return {
        "source_file": source_file,
        "source_field": column_name,

        # Target model information: only primary mapping fields are passed on
        # as source_value candidates for SupportType.
        "target_concept": TARGET_CONCEPT if is_main_source_value_field else None,
        "target_model": "SupportType" if is_main_source_value_field else None,
        "target_model_field": SOURCE_VALUE_MODEL_FIELD if is_main_source_value_field else None,
        "ontology_class": TARGET_CONCEPT if is_main_source_value_field else None,

        # Calibrated output
        "confidence": confidence,
        "threshold": ACCEPTANCE_THRESHOLD,
        "field_role": field_role,
        "role_reason": role_reason,
        "status": _status_from_role(field_role),
        "is_main_source_value_field": is_main_source_value_field,

        # Evidence for UI / terminal explanation
        "evidence": {
            "log_odds": round(log_odds, 3),
            "signals": {k: round(v, 3) for k, v in signals.items()},
            "contributions": contributions,
            "value_diagnostics": value_diagnostics,
            "description_field": description_field,
            "role_reason": role_reason,
        },

        # Backwards-compatible fields used by matcher/UI
        "matched_values": (
            value_diagnostics["matched_target_values"]
            + value_diagnostics["matched_source_hints"]
        ),
        "rationale": rationale,
        "source_description_field": description_field,
    }


def _build_rationale(
    name_signals: dict[str, float],
    value_signals: dict[str, float],
    value_diagnostics: dict[str, Any],
    field_role: str,
    role_reason: str,
) -> str:
    parts: list[str] = []

    if name_signals["name_exact_target_field"]:
        parts.append("column name matches the SupportType target field exactly")
    elif name_signals["name_pattern_specificity"] > 0:
        parts.append(
            f"column name matches a SupportType pattern "
            f"(specificity={name_signals['name_pattern_specificity']:.2f})"
        )

    if value_diagnostics["matched_target_values"]:
        parts.append(
            "sample values include ontology enums: "
            + ", ".join(value_diagnostics["matched_target_values"])
        )

    if value_diagnostics["matched_source_hints"]:
        parts.append(
            "sample values include known source-system hints: "
            + ", ".join(value_diagnostics["matched_source_hints"])
        )

    if name_signals["name_in_negative_list"]:
        parts.append("column name is in the known-negative list")
    if name_signals["is_description_column"]:
        parts.append("column appears to be a description/label column, not a code")
    if value_signals["values_look_numeric"] >= 0.5:
        parts.append("values look numeric")
    if value_signals["values_look_like_dates"] >= 0.5:
        parts.append("values look like dates")
    if value_signals["values_freeform_high_cardinality"]:
        parts.append("values look like freeform high-cardinality text")

    parts.append(f"role={field_role}: {role_reason}")

    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def _read_csv(file_path: Path) -> list[dict[str, Any]]:
    with open(file_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def read_csv_samples(file_path: Path, sample_size: int = 30) -> dict[str, list[str]]:
    """Read a small sample of values from each CSV column."""

    with open(file_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            raise ValueError(f"No columns found in {file_path}")

        samples = {column: [] for column in reader.fieldnames}

        for index, row in enumerate(reader):
            if index >= sample_size:
                break
            for column in reader.fieldnames:
                samples[column].append(row.get(column, ""))

    return samples


def get_support_type_model_rules() -> dict[str, Any]:
    required = [
        name
        for name, info in SupportType.model_fields.items()
        if info.is_required()
    ]

    return {
        "target_concept": TARGET_CONCEPT,
        "target_model": "SupportType",
        "target_model_fields": sorted(SUPPORT_TYPE_MODEL_FIELDS),
        "required_fields": required,
        "source_value_model_field": SOURCE_VALUE_MODEL_FIELD,
        "target_value_field": SUPPORT_TYPE_TARGET_FIELD,
        "target_group_field": SUPPORT_GROUP_TARGET_FIELD,
        "allowed_support_types": sorted(ALLOWED_SUPPORT_TYPES),
        "allowed_support_groups": sorted(ALLOWED_SUPPORT_GROUPS),
        "provenance_fields": sorted(PROVENANCE_MODEL_FIELDS),
        "mapping_trace_fields": sorted(MAPPING_TRACE_MODEL_FIELDS),
    }



def _suggest_target_value(raw_value: Any) -> str:
    """Suggest an ontology value for one raw source value.

    The reasoner should not invent final mappings, but it can pre-fill obvious
    source values so the Mapping Workbench does not default valid values such as
    "Activity support" to UnknownNeedsReview. Broad values such as GRUND stay
    as UnknownNeedsReview because they are not specific enough to distinguish
    StudyGrant from StudyLoan.
    """

    normalized = _normalize_text(raw_value)

    if normalized in SOURCE_VALUE_TO_SUPPORT_TYPE:
        return SOURCE_VALUE_TO_SUPPORT_TYPE[normalized]

    underscore_normalized = normalized.replace(" ", "_").replace("-", "_")
    if underscore_normalized in SOURCE_VALUE_TO_SUPPORT_TYPE:
        return SOURCE_VALUE_TO_SUPPORT_TYPE[underscore_normalized]

    return "UnknownNeedsReview"


def _build_suggested_target_value_map(sample_values: list[Any]) -> dict[str, str]:
    """Build source value -> suggested SupportType ontology value map."""

    suggestions: dict[str, str] = {}

    for value in sample_values:
        if value is None or str(value).strip() == "":
            continue

        raw = str(value).strip()
        suggestions[raw] = _suggest_target_value(raw)

    return dict(sorted(suggestions.items()))


def _build_suggested_target_group_map(
    suggested_target_value_map: dict[str, str],
) -> dict[str, Optional[str]]:
    """Build source value -> suggested SupportGroup map from SupportType suggestions."""

    return {
        source_value: SUPPORT_TYPE_TO_GROUP.get(target_value)
        for source_value, target_value in suggested_target_value_map.items()
    }

def _build_payload(
    csv_file_name: str,
    column_name: str,
    sample_values: list[Any],
    classification: dict[str, Any],
) -> dict[str, Any]:
    field_role = classification["field_role"]

    suggested_target_value_map = _build_suggested_target_value_map(sample_values)
    suggested_target_group_map = _build_suggested_target_group_map(
        suggested_target_value_map
    )
    has_unknown_suggestions = any(
        target_value == "UnknownNeedsReview"
        for target_value in suggested_target_value_map.values()
    )

    return {
        "id": f"{csv_file_name}::{column_name}",
        "name": column_name,
        "field": column_name,
        "file": csv_file_name,
        "type": "categorical",
        "status": classification["status"],
        "color": _color_from_role(field_role),
        "field_role": field_role,
        "role_reason": classification["role_reason"],

        "concept": TARGET_CONCEPT if classification["is_main_source_value_field"] else None,
        "target_concept": classification["target_concept"],
        "target_model": classification["target_model"],
        "target_model_field": classification["target_model_field"],
        "matching_role": (
            "candidate_source_value_field"
            if classification["is_main_source_value_field"]
            else None
        ),

        "confidence": classification["confidence"],
        "threshold": classification["threshold"],
        "samples": sample_values[:10],
        "source_values": sorted(
            {str(v).strip() for v in sample_values if v is not None and str(v).strip() != ""}
        ),
        "matched_values": classification["matched_values"],
        "rationale": classification["rationale"],
        "evidence": classification["evidence"],
        "source_description_field": classification["source_description_field"],

        # Used by the Mapping Workbench so obvious values do not default to
        # UnknownNeedsReview. The user can still override these before submit.
        "suggested_target_value_map": suggested_target_value_map,
        "suggested_target_group_map": suggested_target_group_map,
        "has_unknown_suggestions": has_unknown_suggestions,

        "model_rules": get_support_type_model_rules(),
    }


def run_support_type_reasoner(
    person_id: str = "20000421-1234",
    data_dir: Optional[Path] = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """
    Run the SupportType reasoner across CSV files in ``data_dir``.

    Returns a structured payload consumed by the matcher and the demo UI.
    Only ``fields`` should be sent automatically to the matcher/transformer.
    Review/context/rejected fields are returned so the UI can explain the
    reasoner's decision.
    """

    if data_dir is None:
        data_dir = DATA_DIR

    accepted_fields: list[dict[str, Any]] = []
    review_fields: list[dict[str, Any]] = []
    context_fields: list[dict[str, Any]] = []
    rejected_fields: list[dict[str, Any]] = []
    empty_fields: list[dict[str, Any]] = []

    csv_files = sorted(data_dir.glob("*.csv"))
    file_summaries: list[dict[str, Any]] = []

    for csv_file in csv_files:
        rows = _read_csv(csv_file)
        if not rows:
            file_summaries.append(
                {
                    "file": csv_file.name,
                    "rows": 0,
                    "person_rows": 0,
                    "columns": 0,
                    "status": "empty_file",
                }
            )
            continue

        all_columns = list(rows[0].keys())

        person_rows = [
            r for r in rows
            if any(r.get(f) == person_id for f in PERSON_ID_FIELDS)
        ]
        sample_rows = person_rows if person_rows else rows

        file_summary = {
            "file": csv_file.name,
            "rows": len(rows),
            "person_rows": len(person_rows),
            "columns": len(all_columns),
            "status": "person_rows_found" if person_rows else "schema_fallback",
        }
        file_summaries.append(file_summary)

        for column_name in all_columns:
            sample_values = [
                row.get(column_name)
                for row in sample_rows
                if row.get(column_name) not in (None, "")
            ]

            if not sample_values:
                empty_fields.append(
                    {
                        "id": f"{csv_file.name}::{column_name}",
                        "file": csv_file.name,
                        "field": column_name,
                        "name": column_name,
                        "status": "empty",
                        "field_role": "empty_field",
                        "confidence": 0.0,
                        "whySkipped": "Column has no non-empty sample values for this person or fallback sample.",
                    }
                )
                continue

            classification = score_column(
                source_file=csv_file.name,
                column_name=column_name,
                sample_values=sample_values[:50],
                all_columns=all_columns,
            )

            payload = _build_payload(
                csv_file_name=csv_file.name,
                column_name=column_name,
                sample_values=sample_values,
                classification=classification,
            )

            if payload["field_role"] == "primary_mapping_field":
                accepted_fields.append(payload)
            elif payload["field_role"] == "review_field":
                review_fields.append(payload)
            elif payload["field_role"] in {"context_field", "evidence_field", "descriptor_field"}:
                context_fields.append(payload)
            else:
                rejected_fields.append(payload)

    considered_fields = review_fields + context_fields + rejected_fields

    result = {
        "target_concept": TARGET_CONCEPT,
        "target_model": "SupportType",
        "person_id": person_id,
        "data_dir": str(data_dir),
        "files_scanned": len(csv_files),
        "file_summaries": file_summaries,
        "model_rules": get_support_type_model_rules(),

        # Backwards-compatible: matcher should continue reading result["fields"].
        "fields": accepted_fields,
        "considered_fields": considered_fields,
        "other_fields": empty_fields,

        # New explicit groups for UI and terminal output.
        "review_fields": review_fields,
        "context_fields": context_fields,
        "rejected_fields": rejected_fields,
        "empty_fields": empty_fields,

        "summary": {
            "accepted_primary_mapping_fields": len(accepted_fields),
            "review_fields": len(review_fields),
            "context_or_evidence_fields": len(context_fields),
            "rejected_fields": len(rejected_fields),
            "empty_fields": len(empty_fields),
            "total_fields_checked": (
                len(accepted_fields)
                + len(review_fields)
                + len(context_fields)
                + len(rejected_fields)
                + len(empty_fields)
            ),
        },
        "scoring_model": {
            "type": "calibrated_logistic_with_field_roles",
            "weights": SIGNAL_WEIGHTS,
            "threshold": ACCEPTANCE_THRESHOLD,
            "primary_source_field_names": sorted(PRIMARY_SOURCE_FIELD_NAMES),
            "context_exact_fields": sorted(CONTEXT_EXACT_FIELDS),
            "evidence_exact_fields": sorted(EVIDENCE_EXACT_FIELDS),
        },
    }

    if verbose:
        print_reasoner_terminal_report(result)

    return result


# ---------------------------------------------------------------------------
# Clear terminal output
# ---------------------------------------------------------------------------

def _short_list(values: list[Any], max_items: int = 4) -> str:
    cleaned = [str(v) for v in values if v not in (None, "")]
    if not cleaned:
        return "-"
    shown = cleaned[:max_items]
    suffix = "" if len(cleaned) <= max_items else f" … +{len(cleaned) - max_items} more"
    return ", ".join(shown) + suffix


def _print_field_group(title: str, fields: list[dict[str, Any]], max_rows: int) -> None:
    print()
    print(title)
    print("-" * len(title))

    if not fields:
        print("  None")
        return

    sorted_fields = sorted(fields, key=lambda f: f.get("confidence", 0), reverse=True)

    for field in sorted_fields[:max_rows]:
        description_field = field.get("source_description_field") or "-"
        matched_values = _short_list(field.get("matched_values", []))
        samples = _short_list(field.get("samples", []))

        print(
            f"  {field['file']}.{field['name']} | "
            f"confidence={field.get('confidence', 0):.3f} | "
            f"role={field.get('field_role')}"
        )
        print(f"    samples: {samples}")
        print(f"    matched values: {matched_values}")
        print(f"    description field: {description_field}")
        print(f"    why: {field.get('role_reason', field.get('rationale', '-'))}")

    if len(fields) > max_rows:
        print(f"  … {len(fields) - max_rows} more not shown")


def print_reasoner_terminal_report(
    result: dict[str, Any],
    max_rows_per_section: int = 12,
) -> None:
    """Print a readable reasoner report for terminal debugging."""

    summary = result["summary"]

    print()
    print("=" * 78)
    print("SUPPORTTYPE REASONER REPORT")
    print("=" * 78)
    print(f"Person ID:             {result['person_id']}")
    print(f"Target concept:        {result['target_concept']}")
    print(f"Data folder:           {result['data_dir']}")
    print(f"CSV files scanned:     {result['files_scanned']}")
    print(f"Acceptance threshold:  {result['scoring_model']['threshold']}")
    print(f"Scoring model:         {result['scoring_model']['type']}")

    print()
    print("File scan summary")
    print("-----------------")
    for item in result["file_summaries"]:
        print(
            f"  {item['file']} | rows={item['rows']} | "
            f"person_rows={item['person_rows']} | columns={item['columns']} | "
            f"{item['status']}"
        )

    print()
    print("Decision summary")
    print("----------------")
    print(f"  Accepted primary mapping fields: {summary['accepted_primary_mapping_fields']}")
    print(f"  Review fields:                   {summary['review_fields']}")
    print(f"  Context/evidence/descriptor:     {summary['context_or_evidence_fields']}")
    print(f"  Rejected fields:                 {summary['rejected_fields']}")
    print(f"  Empty fields:                    {summary['empty_fields']}")
    print(f"  Total fields checked:            {summary['total_fields_checked']}")

    _print_field_group(
        "ACCEPTED — sent to matcher/transformer",
        result["fields"],
        max_rows=max_rows_per_section,
    )
    _print_field_group(
        "REVIEW — possible candidate, not auto-sent",
        result["review_fields"],
        max_rows=max_rows_per_section,
    )
    _print_field_group(
        "CONTEXT / EVIDENCE / DESCRIPTOR — useful, but not primary mapping input",
        result["context_fields"],
        max_rows=max_rows_per_section,
    )
    _print_field_group(
        "REJECTED — not a SupportType source-value field",
        result["rejected_fields"],
        max_rows=max_rows_per_section,
    )

    print()
    print("=" * 78)
    print("End of reasoner report")
    print("=" * 78)


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------

def run_support_type_reasoner_on_csv(file_path: Path) -> dict[str, Any]:
    """Run the SupportType reasoner on one CSV file.

    This returns the same frontend/API-friendly shape as run_support_type_reasoner(),
    instead of returning raw score_column() objects. This keeps uploaded-file runs
    consistent with full-folder runs.
    """

    samples = read_csv_samples(file_path)
    all_columns = list(samples.keys())

    accepted_fields: list[dict[str, Any]] = []
    review_fields: list[dict[str, Any]] = []
    context_fields: list[dict[str, Any]] = []
    rejected_fields: list[dict[str, Any]] = []
    empty_fields: list[dict[str, Any]] = []

    for column_name, values in samples.items():
        sample_values = [
            value
            for value in values
            if value is not None and str(value).strip() != ""
        ]

        if not sample_values:
            empty_fields.append(
                {
                    "id": f"{file_path.name}::{column_name}",
                    "file": file_path.name,
                    "field": column_name,
                    "name": column_name,
                    "status": "empty",
                    "field_role": "empty_field",
                    "confidence": 0.0,
                    "whySkipped": "Column has no non-empty sample values.",
                }
            )
            continue

        classification = score_column(
            source_file=file_path.name,
            column_name=column_name,
            sample_values=sample_values[:50],
            all_columns=all_columns,
        )

        payload = _build_payload(
            csv_file_name=file_path.name,
            column_name=column_name,
            sample_values=sample_values,
            classification=classification,
        )

        if payload["field_role"] == "primary_mapping_field":
            accepted_fields.append(payload)
        elif payload["field_role"] == "review_field":
            review_fields.append(payload)
        elif payload["field_role"] in {"context_field", "evidence_field", "descriptor_field"}:
            context_fields.append(payload)
        else:
            rejected_fields.append(payload)

    considered_fields = review_fields + context_fields + rejected_fields

    return {
        "source_file": file_path.name,
        "target_concept": TARGET_CONCEPT,
        "target_model": "SupportType",
        "model_rules": get_support_type_model_rules(),

        # Same convention as run_support_type_reasoner(): only fields are
        # auto-sent to matcher/transformer. Everything else is review/supporting.
        "fields": accepted_fields,
        "considered_fields": considered_fields,
        "other_fields": empty_fields,
        "review_fields": review_fields,
        "context_fields": context_fields,
        "rejected_fields": rejected_fields,
        "empty_fields": empty_fields,

        "summary": {
            "accepted_primary_mapping_fields": len(accepted_fields),
            "review_fields": len(review_fields),
            "context_or_evidence_fields": len(context_fields),
            "rejected_fields": len(rejected_fields),
            "empty_fields": len(empty_fields),
            "total_fields_checked": (
                len(accepted_fields)
                + len(review_fields)
                + len(context_fields)
                + len(rejected_fields)
                + len(empty_fields)
            ),
        },
    }


def run_support_type_reasoner_on_all_csvs(
    data_dir: Path = DATA_DIR,
) -> list[dict[str, Any]]:
    """Run the SupportType reasoner on all CSV files in data/raw."""

    return [
        run_support_type_reasoner_on_csv(file_path)
        for file_path in sorted(data_dir.glob("*.csv"))
    ]


if __name__ == "__main__":
    run_support_type_reasoner(verbose=True)
