"""
FastAPI surface for the SupportType pipeline.

What changed from the previous version
--------------------------------------
Re-pointed at the new three-stage pipeline (``src.new.*``) and wired the
rule-authoring + storage layers in:

    1. /api/income/support-type/reasoner/upload
       Uploads CSVs and runs the reasoner. Same contract as before, plus
       the ``scoring_model`` (weights + threshold) is now included in the
       response so the frontend can render the evidence panel.

    2. /api/income/support-type/submit-mapping
       Persists each approved mapping as a *user rule* via
       ``src.new.storage.save_user_rule``, then runs matcher and
       transformer. The transformer auto-persists its result to
       ``src/storage/transformations/``, so the response carries a stable
       ``transformation_id`` the frontend can revisit later.

    3. Rule + transformation management endpoints (new):
         GET    /api/income/support-type/rules
         GET    /api/income/support-type/rules/system
         GET    /api/income/support-type/rules/user
         DELETE /api/income/support-type/rules/user/{rule_id}
         GET    /api/income/support-type/transformations
         GET    /api/income/support-type/transformations/{transformation_id}

Why two rule stores
-------------------
The interactive flow does NOT mutate ``src/mappings/*.json``. Those remain
governance-approved system rules, edited via code review. User-authored
rules submitted at runtime live in ``src/storage/user_rules/`` and are
picked up by the matcher automatically on later runs. This keeps the
distinction between "approved by review" and "approved by user click"
visible end-to-end.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.new.matcher_st import match_support_type
from src.new.reasoner_st import run_support_type_reasoner
from src.new.rule_st import (
    ALLOWED_SUPPORT_GROUPS,
    ALLOWED_SUPPORT_TYPES,
)
from src.new.storage_st import (
    delete_user_rule,
    list_transformations,
    load_all_rules,
    load_system_rules,
    load_transformation,
    load_user_rules,
    save_user_rule,
)
from src.new.transformer_st import transform_support_type_matches


app = FastAPI(title="SupportType pipeline API")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = PROJECT_ROOT / "data" / "uploaded"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


# ---------------------------------------------------------------------------
# Logging + utilities
# ---------------------------------------------------------------------------

def log_step(message: str) -> None:
    print(f"\n[API] {message}", flush=True)


def to_jsonable(value: Any) -> Any:
    """
    Coerce Pydantic models / nested objects into JSON-safe values.

    The new transformer already model_dumps successful objects, but matcher
    output can still carry nested structures we want flattened before sending
    over the wire.
    """

    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    return value


def _stable_user_rule_id(
    source_file: str,
    source_field: str,
    fallback_id: Optional[str],
) -> str:
    """
    Pick a stable, idempotent id for a user-authored rule.

    Frontend-supplied ids win. Otherwise we derive a deterministic id from
    ``(source_file, source_field)`` so re-submitting the same mapping
    overwrites the previous user rule on disk instead of stacking copies.
    """

    if fallback_id:
        return fallback_id

    clean_file = source_file.replace(".csv", "")
    return f"user.{clean_file}.{source_field}"


def convert_frontend_mapping_to_rule(
    mapping: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    Convert one mapping payload from the frontend into a matcher/transformer
    rule dict, or return ``None`` if the mapping cannot be approved.

    A mapping is converted only if:

      * ``status == "accepted"``
      * ``source_file`` and ``source_field`` are present
      * the value map is non-empty after filtering ``UnknownNeedsReview``

    The returned dict follows the same shape as rules in
    ``src/mappings/support_type.json``, which is what both the matcher and
    the storage layer expect.
    """

    if mapping.get("status") != "accepted":
        return None

    source_file = mapping.get("file") or mapping.get("source_file")
    source_field = mapping.get("name") or mapping.get("source_field")
    if not source_file or not source_field:
        log_step(f"Skipped mapping without source_file/source_field: {mapping}")
        return None

    raw_value_map = (
        mapping.get("target_value_map")
        or mapping.get("suggested_target_value_map")
        or {}
    )

    value_map = {
        str(source_value): target_value
        for source_value, target_value in raw_value_map.items()
        if target_value and target_value != "UnknownNeedsReview"
    }

    if not value_map:
        log_step(
            f"Skipped mapping with no approved value map: "
            f"{source_file}.{source_field}"
        )
        return None

    rule_id = _stable_user_rule_id(
        source_file=source_file,
        source_field=source_field,
        fallback_id=mapping.get("mapping_rule_id") or mapping.get("id"),
    )

    rule: dict[str, Any] = {
        "id": rule_id,
        "target_class": "SupportType",
        "target_property": "supportType",
        "source_file": source_file,
        "source_field": source_field,
        "source_value_field": mapping.get("source_value_field") or source_field,
        "target_value_map": value_map,
        "rationale": (
            mapping.get("rationale")
            or "Approved through the mapping workbench."
        ),
    }

    # Optional fields: pass through if the frontend provided them.
    if mapping.get("description_field"):
        rule["description_field"] = mapping["description_field"]
    if mapping.get("target_group_map"):
        rule["target_group_map"] = mapping["target_group_map"]
    if mapping.get("target_group"):
        rule["target_group"] = mapping["target_group"]

    return rule


def _validate_rule_target_values(rule: dict[str, Any]) -> list[str]:
    """
    Return a list of human-readable validation errors for the rule's target
    values. Caller decides whether to 4xx out of the request.
    """

    errors: list[str] = []
    value_map = rule.get("target_value_map") or {}
    target_value = rule.get("target_value")

    bad_types = [
        v for v in list(value_map.values()) + ([target_value] if target_value else [])
        if v not in ALLOWED_SUPPORT_TYPES
    ]
    if bad_types:
        errors.append(
            f"Unknown SupportType target value(s) {bad_types}. "
            f"Allowed: {sorted(ALLOWED_SUPPORT_TYPES)}"
        )

    group_map = rule.get("target_group_map") or {}
    target_group = rule.get("target_group")
    bad_groups = [
        v for v in list(group_map.values()) + ([target_group] if target_group else [])
        if v not in ALLOWED_SUPPORT_GROUPS
    ]
    if bad_groups:
        errors.append(
            f"Unknown SupportGroup target value(s) {bad_groups}. "
            f"Allowed: {sorted(ALLOWED_SUPPORT_GROUPS)}"
        )

    return errors


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class RequestBody(BaseModel):
    category: str


class TransformRequest(BaseModel):
    concept: str
    person_id: str = "20000421-1234"


class SubmitMappingRequest(BaseModel):
    run_id: Optional[str] = None
    person_id: str = "20000421-1234"
    concept: str = "SupportType"
    mappings: list[dict[str, Any]]
    # New: who approved these mappings. Recorded in the user-rules envelope
    # for audit. Defaults to "frontend" if the UI does not pass an author.
    author: str = "frontend"


# ---------------------------------------------------------------------------
# Basic routes
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "status": "NEW BACKEND IS LIVE",
        "pipeline_modules": "src.new.*",
        "rule_stores": [
            "src/mappings/  (system, read-only)",
            "src/storage/user_rules/  (runtime-authored)",
        ],
    }


# ---------------------------------------------------------------------------
# Generic concept-stage runner (kept for ad-hoc debugging)
# ---------------------------------------------------------------------------

CONCEPT_MODULES = {
    "support-type": {
        "reasoner": "src.new.reasoner_st",
        "matcher": "src.new.matcher_st",
        "transformer": "src.new.transformer_st",
        "pipeline": "src.new.pipeline",
        "model": "src.new.model_st",
        "storage": "src.new.storage",
        # Backwards-compatible alias for the old "transform" stage key.
        "transform": "src.new.transformer_st",
    },
}


@app.post("/api/run-{concept_kebab}-{stage_key}-file")
def run_concept_stage_file(concept_kebab: str, stage_key: str):
    if concept_kebab not in CONCEPT_MODULES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown concept: {concept_kebab}",
        )

    stages = CONCEPT_MODULES[concept_kebab]
    if stage_key not in stages:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage_key}' for concept '{concept_kebab}'",
        )

    module = stages[stage_key]
    try:
        completed = subprocess.run(
            [sys.executable, "-m", module],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {
            "command": f"python -m {module}",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail=f"{concept_kebab} {stage_key} took too long to run.",
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


# ---------------------------------------------------------------------------
# Interactive flow, step 1: upload CSVs + run reasoner
# ---------------------------------------------------------------------------

@app.post("/api/income/support-type/reasoner/upload")
async def upload_and_run_support_type_reasoner(
    person_id: str = Form("20000421-1234"),
    concept: str = Form("SupportType"),
    files: list[UploadFile] = File(...),
):
    """
    1. Receives uploaded CSV files.
    2. Saves them to ``data/uploaded/<run_id>/``.
    3. Runs the SupportType reasoner on those uploaded files.
    4. Stops before matching/transformation so the frontend can show the
       Mapping Workbench.
    """

    run_id = uuid.uuid4().hex[:8]
    run_dir = UPLOAD_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    log_step("STEP 1: Upload received")
    log_step(f"Person ID: {person_id}")
    log_step(f"Concept: {concept}")
    log_step(f"Run ID: {run_id}")
    log_step(f"Upload folder: {run_dir}")

    saved_files: list[str] = []
    for uploaded_file in files:
        filename = Path(uploaded_file.filename or "").name

        if not filename.lower().endswith(".csv"):
            raise HTTPException(
                status_code=400,
                detail=f"Only CSV files are supported. Invalid file: {filename}",
            )

        destination = run_dir / filename
        with destination.open("wb") as buffer:
            shutil.copyfileobj(uploaded_file.file, buffer)

        saved_files.append(filename)
        log_step(f"Saved CSV file: {destination}")

    log_step("STEP 2: Running SupportType reasoner")
    try:
        reasoner_output = run_support_type_reasoner(
            person_id=person_id,
            data_dir=run_dir,
        )
    except TypeError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "run_support_type_reasoner() must accept person_id and data_dir. "
                f"Original error: {error}"
            ),
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    fields = reasoner_output.get("fields", [])
    considered_fields = reasoner_output.get("considered_fields", [])
    other_fields = reasoner_output.get("other_fields", [])
    scoring_model = reasoner_output.get("scoring_model")

    log_step("STEP 3: Reasoner finished")
    log_step(
        f"Accepted: {len(fields)} · "
        f"Considered: {len(considered_fields)} · "
        f"Empty: {len(other_fields)}"
    )
    log_step("STEP 4: Pipeline paused for mapping review")

    return {
        "status": "paused_for_mapping_review",
        "run_id": run_id,
        "concept": concept,
        "person_id": person_id,
        "uploaded_files": saved_files,
        "fields": fields,
        "considered_fields": considered_fields,
        "other_fields": other_fields,
        # NEW: weights + threshold so the UI can render the evidence panel.
        "scoring_model": scoring_model,
        "next_step": "Review mappings in the frontend, then submit approved mappings.",
    }


# ---------------------------------------------------------------------------
# Interactive flow, step 2: submit approved mappings -> match + transform
# ---------------------------------------------------------------------------

@app.post("/api/income/support-type/submit-mapping")
def submit_support_type_mapping(body: SubmitMappingRequest):
    """
    Receives approved/edited mappings from the frontend.

    1. Converts each frontend mapping into a matcher/transformer rule.
    2. Validates target values against the SupportType ontology enums.
    3. Persists each rule into ``src/storage/user_rules/`` so future runs
       pick it up automatically.
    4. Runs matcher with the exact submitted rules (deterministic).
    5. Runs transformer, which also persists the result to
       ``src/storage/transformations/``.
    6. Returns matcher + transformer output plus saved-rule IDs and a
       stable ``transformation_id``.
    """

    log_step("STEP 5: Approved mappings received from frontend")
    log_step(f"Run ID: {body.run_id}")
    log_step(f"Person ID: {body.person_id}")
    log_step(f"Mappings received: {len(body.mappings)}")
    log_step(f"Author: {body.author}")

    # 1. Convert frontend payload -> rule dicts
    approved_rules: list[dict[str, Any]] = []
    for mapping in body.mappings:
        rule = convert_frontend_mapping_to_rule(mapping)
        if rule:
            approved_rules.append(rule)

    log_step(f"Approved transformer rules created: {len(approved_rules)}")
    if not approved_rules:
        raise HTTPException(
            status_code=400,
            detail=(
                "No approved mappings could be converted into transformer rules. "
                "Check that mappings have status='accepted', file/name, and a value map."
            ),
        )

    # 2. Defense-in-depth validation. The frontend should already enforce
    #    this, but a typo in the payload should not silently corrupt the
    #    user-rules store.
    validation_errors: list[str] = []
    for rule in approved_rules:
        for err in _validate_rule_target_values(rule):
            validation_errors.append(f"{rule['id']}: {err}")

    if validation_errors:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "One or more approved mappings have invalid target values.",
                "errors": validation_errors,
            },
        )

    # 3. Persist each approved rule as a user rule. This is the
    #    "actively create mapping rules" capability -- these rules survive
    #    the request and are loaded automatically by future matcher runs.
    saved_rule_ids: list[str] = []
    for rule in approved_rules:
        try:
            saved_id = save_user_rule(
                rule=rule,
                author=body.author,
                rationale=rule.get("rationale"),
                rule_id=rule.get("id"),
            )
            saved_rule_ids.append(saved_id)
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=f"Rule {rule.get('id')} rejected by storage: {error}",
            )

    log_step(f"Persisted user rules: {saved_rule_ids}")

    # 4. Resolve the data folder for this run.
    if body.run_id:
        run_dir = UPLOAD_ROOT / body.run_id
    else:
        run_dir = RAW_DATA_DIR

    if not run_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Run/data folder not found: {run_dir}",
        )

    # 5. Matcher. We pass the EXACT rules just submitted (not the merged
    #    system+user set from storage) so this request's result is
    #    deterministic with respect to the frontend payload. The persisted
    #    rules from step 3 will affect *future* runs that load from storage.
    log_step("STEP 6: Running matcher with submitted rules")
    try:
        matcher_output = match_support_type(
            person_id=body.person_id,
            data_dir=run_dir,
            mappings=approved_rules,
        )
    except TypeError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "match_support_type() must accept person_id, data_dir, and mappings. "
                f"Original error: {error}"
            ),
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

       # 6. Transformer.
    # The current transformer does not accept persist=True, so do not pass it here.
    log_step("STEP 7: Running transformer")
    try:
        transformer_output = transform_support_type_matches(matcher_output)
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    transformation_id = (
        transformer_output.get("transformation_id")
        if isinstance(transformer_output, dict)
        else None
    )

    object_count = 0
    if isinstance(transformer_output, dict):
        object_count = len(
            transformer_output.get("matches")
            or transformer_output.get("objects")
            or transformer_output.get("results")
            or []
        )

    log_step(
        f"STEP 8: Transformer finished. "
        f"transformation_id={transformation_id} "
        f"objects={object_count}"
    )

    return {
        "status": "completed",
        "concept": body.concept,
        "person_id": body.person_id,
        "run_id": body.run_id,
        "transformation_id": transformation_id,
        "message": (
            "Mappings submitted. Each approved mapping was persisted as a user "
            "rule and the matcher + transformer ran against the submitted rules."
        ),
        "steps_executed": [
            "frontend mappings received",
            "frontend mappings converted into matcher/transformer rules",
            "target values validated against the SupportType ontology",
            "each approved mapping persisted as a user rule",
            "matcher matched person rows against the submitted rules",
            "transformer applied mappings and validated SupportType objects",
            "transformation returned to frontend",
        ],
        "saved_user_rule_ids": saved_rule_ids,
        "approved_rules": approved_rules,
        "matcher": to_jsonable(matcher_output),
        "output": to_jsonable(transformer_output),
    }


# ---------------------------------------------------------------------------
# Rule management
# ---------------------------------------------------------------------------

@app.get("/api/income/support-type/rules")
def list_all_rules_endpoint():
    """
    Return both rule stores. Each rule carries ``_origin`` ('system' or
    'user') so the frontend can render them distinctly.
    """
    return {
        "system": load_system_rules("SupportType"),
        "user": load_user_rules("SupportType"),
        "all": load_all_rules("SupportType"),
    }


@app.get("/api/income/support-type/rules/system")
def list_system_rules_endpoint():
    return {"rules": load_system_rules("SupportType")}


@app.get("/api/income/support-type/rules/user")
def list_user_rules_endpoint():
    return {"rules": load_user_rules("SupportType")}


@app.delete("/api/income/support-type/rules/user/{rule_id}")
def delete_user_rule_endpoint(rule_id: str):
    deleted = delete_user_rule(rule_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"No user rule with id {rule_id}",
        )
    return {"deleted": rule_id}


# ---------------------------------------------------------------------------
# Transformation history
# ---------------------------------------------------------------------------

@app.get("/api/income/support-type/transformations")
def list_transformations_endpoint():
    return {"transformations": list_transformations()}


@app.get("/api/income/support-type/transformations/{transformation_id}")
def get_transformation_endpoint(transformation_id: str):
    try:
        return load_transformation(transformation_id)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail=f"No transformation with id {transformation_id}",
        )
