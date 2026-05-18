"""
Persistence layer for the SupportType pipeline.

Two separate stores live on disk, on purpose:

    src/mappings/                  -- "system" rules, curated and reviewed.
                                      Treated as source of truth and not
                                      written to from this module.

    src/storage/user_rules/        -- "user" rules authored at runtime via
                                      the UI / rule_authoring module. These
                                      are also approved mapping rules, but
                                      separated so they can be reviewed,
                                      promoted, or rolled back independently.

    src/storage/transformations/   -- transformer outputs, one JSON per run,
                                      plus an index.json the UI uses to list
                                      past runs without scanning the folder.

Why two stores
--------------
A consultancy-grade pipeline needs a clear distinction between rules that
are governance-approved and rules a user just typed in. Mixing them into a
single file gives you no way to talk about provenance, no way to roll back
a bad authoring session, and no way to PR-review changes.

JSON files on disk are deliberate. They diff well, they version well in
git, and they are the lingua franca every downstream tool already speaks.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

SYSTEM_RULES_DIR = PROJECT_ROOT / "src" / "mappings"
USER_RULES_DIR = PROJECT_ROOT / "src" / "storage" / "user_rules"
TRANSFORMATIONS_DIR = PROJECT_ROOT / "src" / "storage" / "transformations"
TRANSFORMATIONS_INDEX = TRANSFORMATIONS_DIR / "index.json"


def _ensure_dirs() -> None:
    USER_RULES_DIR.mkdir(parents=True, exist_ok=True)
    TRANSFORMATIONS_DIR.mkdir(parents=True, exist_ok=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Rule loading (system + user merged)
# ---------------------------------------------------------------------------

def load_system_rules(concept: str = "SupportType") -> list[dict[str, Any]]:
    """Load rules from the curated system-rules folder for ``concept``."""

    # We support a per-concept filename like support_type.json. Anything
    # else in src/mappings/ is concept-specific and parsed by its concept
    # module; here we read the support_type one.
    if concept != "SupportType":
        raise NotImplementedError(
            f"System rules loader currently only supports SupportType, not {concept}"
        )

    path = SYSTEM_RULES_DIR / "support_type.json"
    if not path.exists():
        return []

    payload = json.loads(path.read_text(encoding="utf-8"))
    rules = payload.get("rules", [])

    for r in rules:
        r.setdefault("_origin", "system")
        r.setdefault("_origin_file", str(path.relative_to(PROJECT_ROOT)))

    return rules


def load_user_rules(concept: str = "SupportType") -> list[dict[str, Any]]:
    """Load all user-authored rules for ``concept`` from individual files."""

    _ensure_dirs()
    rules: list[dict[str, Any]] = []

    for path in sorted(USER_RULES_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        rule = payload.get("rule")
        if not rule:
            continue
        if rule.get("target_class") != concept and concept != "*":
            continue

        rule.setdefault("_origin", "user")
        rule.setdefault("_origin_file", str(path.relative_to(PROJECT_ROOT)))
        rule.setdefault("_author", payload.get("author"))
        rule.setdefault("_created_at", payload.get("created_at"))
        rule.setdefault("id", payload.get("id"))

        rules.append(rule)

    return rules


def load_all_rules(concept: str = "SupportType") -> list[dict[str, Any]]:
    """Return system + user rules merged. System rules come first."""

    return load_system_rules(concept) + load_user_rules(concept)


# ---------------------------------------------------------------------------
# User rule authoring
# ---------------------------------------------------------------------------

def save_user_rule(
    rule: dict[str, Any],
    author: str,
    rationale: Optional[str] = None,
    rule_id: Optional[str] = None,
) -> str:
    """
    Save a user-authored mapping rule. Returns the rule ID.

    The rule itself follows the same shape as system rules in
    src/mappings/support_type.json. We wrap it with an envelope that
    records author and timestamp.
    """

    _ensure_dirs()

    if "source_file" not in rule or "source_field" not in rule:
        raise ValueError("Rule must include source_file and source_field")
    if "target_class" not in rule:
        raise ValueError("Rule must include target_class")
    if "target_value" not in rule and "target_value_map" not in rule:
        raise ValueError("Rule must include target_value or target_value_map")

    if rule_id is None:
        short = uuid.uuid4().hex[:8]
        source_field = rule.get("source_field", "field")
        source_file = rule.get("source_file", "file").replace(".csv", "")
        rule_id = f"user.{source_file}.{source_field}.{short}"

    if rationale and not rule.get("rationale"):
        rule["rationale"] = rationale
    rule.setdefault("id", rule_id)

    envelope = {
        "id": rule_id,
        "author": author,
        "created_at": _utc_now_iso(),
        "rule": rule,
    }

    out = USER_RULES_DIR / f"{rule_id}.json"
    out.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
    return rule_id


def delete_user_rule(rule_id: str) -> bool:
    _ensure_dirs()
    out = USER_RULES_DIR / f"{rule_id}.json"
    if out.exists():
        out.unlink()
        return True
    return False


# ---------------------------------------------------------------------------
# Transformation history
# ---------------------------------------------------------------------------

def save_transformation(result: dict[str, Any]) -> str:
    """
    Persist a transformer result and update the index. Returns the
    transformation ID.
    """

    _ensure_dirs()

    transformation_id = f"st-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    out = TRANSFORMATIONS_DIR / f"{transformation_id}.json"

    payload = dict(result)
    payload["transformation_id"] = transformation_id
    payload["saved_at"] = _utc_now_iso()

    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    index = _load_index()
    summary = payload.get("summary", {})
    index.append(
        {
            "transformation_id": transformation_id,
            "concept": payload.get("concept"),
            "person_id": payload.get("person_id"),
            "saved_at": payload["saved_at"],
            "transformed_object_count": summary.get("transformed_object_count", 0),
            "unmatched_count": summary.get("unmatched_count", 0),
            "filename": out.name,
        }
    )
    _save_index(index)

    return transformation_id


def list_transformations() -> list[dict[str, Any]]:
    return _load_index()


def load_transformation(transformation_id: str) -> dict[str, Any]:
    path = TRANSFORMATIONS_DIR / f"{transformation_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"No transformation with id {transformation_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_index() -> list[dict[str, Any]]:
    if not TRANSFORMATIONS_INDEX.exists():
        return []
    try:
        return json.loads(TRANSFORMATIONS_INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _save_index(index: list[dict[str, Any]]) -> None:
    TRANSFORMATIONS_INDEX.write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    print("System rules:", len(load_system_rules()))
    print("User rules:  ", len(load_user_rules()))
    print("Saved runs:  ", len(list_transformations()))
