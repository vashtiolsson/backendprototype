from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.reasoner.support_type_reasoner import run_support_type_reasoner
from src.transform.support_type import transform_support_type


app = FastAPI()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_ROOT = PROJECT_ROOT / "data" / "uploaded"
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def log_step(message: str) -> None:
    print(f"\n[PIPELINE] {message}", flush=True)


def to_jsonable(value: Any) -> Any:
    """
    Convert Pydantic models or nested objects into JSON-safe values.
    """
    if hasattr(value, "model_dump"):
        return value.model_dump()

    if isinstance(value, list):
        return [to_jsonable(item) for item in value]

    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}

    return value


def convert_frontend_mappings_to_transformer_rules(
    mappings: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert mappings from the frontend Mapping Workbench into the rule format
    expected by transform_support_type().

    Frontend/reasoner shape usually looks like:
      {
        "file": "csn.csv",
        "name": "support_form_code",
        "status": "accepted",
        "suggested_target_value_map": {"GRUNDB": "StudyGrant"}
      }

    Transformer rule shape needs to look like:
      {
        "target_class": "SupportType",
        "source_file": "csn.csv",
        "source_field": "support_form_code",
        "source_value_field": "support_form_code",
        "target_value_map": {"GRUNDB": "StudyGrant"}
      }
    """
    rules: list[dict[str, Any]] = []

    for mapping in mappings:
        if mapping.get("status") != "accepted":
            continue

        source_file = mapping.get("file") or mapping.get("source_file")
        source_field = mapping.get("name") or mapping.get("source_field")

        if not source_file or not source_field:
            log_step(f"Skipped mapping without source_file/source_field: {mapping}")
            continue

        value_map = (
            mapping.get("suggested_target_value_map")
            or mapping.get("target_value_map")
            or {}
        )

        if not value_map:
            log_step(f"Skipped mapping without value map: {source_file}.{source_field}")
            continue

        rule_id = (
            mapping.get("mapping_rule_id")
            or mapping.get("id")
            or f"support.{str(source_file).replace('.csv', '')}.{source_field}"
        )

        rules.append(
            {
                "id": rule_id,
                "target_class": "SupportType",
                "source_file": source_file,
                "source_field": source_field,
                "source_value_field": source_field,
                "target_value_map": value_map,
                "rationale": mapping.get("rationale")
                or "Approved through the mapping workbench.",
            }
        )

    return rules


# -----------------------------------------------------------------------------
# Middleware
# -----------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Request models
# -----------------------------------------------------------------------------

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


# -----------------------------------------------------------------------------
# Basic routes
# -----------------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "NEW BACKEND IS LIVE"}


    return {
        "output": {
            "category": body.category,
            "person_id": person_id,
            "person": to_jsonable(person),
            "support_type": to_jsonable(support_types),
            "amount": to_jsonable(amounts),
            "time_period": to_jsonable(periods),
            "status": to_jsonable(statuses),
            "occupation": to_jsonable(occupations),
        }
    }


# -----------------------------------------------------------------------------
# Generic concept-stage runner
# -----------------------------------------------------------------------------

CONCEPT_MODULES = {
    "support-type": {
        "transform": "src.transform.support_type",
        "reasoner": "src.reasoner.support_type_reasoner",
        "mapping": "src.mappings.support_type",
        "model": "src.models.support_type",
    },
}

@app.post("/api/run-{concept_kebab}-{stage_key}-file")
def run_concept_stage_file(concept_kebab: str, stage_key: str):
    if concept_kebab not in CONCEPT_MODULES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown concept: {concept_kebab}",
        )

    concept_stages = CONCEPT_MODULES[concept_kebab]

    if stage_key not in concept_stages:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage_key}' for concept '{concept_kebab}'",
        )

    module = concept_stages[stage_key]

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


# -----------------------------------------------------------------------------
# Interactive SupportType flow
# Step 1: Upload CSV files and run reasoner
# -----------------------------------------------------------------------------

@app.post("/api/income/support-type/reasoner/upload")
async def upload_and_run_support_type_reasoner(
    person_id: str = Form("20000421-1234"),
    concept: str = Form("SupportType"),
    files: list[UploadFile] = File(...),
):
    """
    1. Receives uploaded CSV files.
    2. Saves them to data/uploaded/<run_id>/.
    3. Runs the SupportType reasoner on those uploaded files.
    4. Stops before mapping/transformation so the frontend can show the
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

    log_step("STEP 3: Reasoner finished")
    log_step(f"Candidate fields returned: {len(fields)}")
    log_step(f"Considered/rejected fields returned: {len(considered_fields)}")
    log_step(f"Other fields returned: {len(other_fields)}")
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
        "next_step": "Review mappings in the frontend, then submit approved mappings.",
    }


# -----------------------------------------------------------------------------
# Interactive SupportType flow
# Step 2: Submit approved mappings and run transformer
# -----------------------------------------------------------------------------

@app.post("/api/income/support-type/submit-mapping")
def submit_support_type_mapping(body: SubmitMappingRequest):
    """
    Receives approved/edited mappings from the frontend.
    Converts them into transformer rules.
    Runs the remaining SupportType transformer steps.
    """

    log_step("STEP 5: Approved mappings received from frontend")
    log_step(f"Run ID: {body.run_id}")
    log_step(f"Person ID: {body.person_id}")
    log_step(f"Mappings received: {len(body.mappings)}")

    approved_rules = convert_frontend_mappings_to_transformer_rules(body.mappings)

    log_step(f"Approved transformer rules created: {len(approved_rules)}")

    if not approved_rules:
        raise HTTPException(
            status_code=400,
            detail=(
                "No approved mappings could be converted into transformer rules. "
                "Check that mappings have status='accepted', file/name, and a value map."
            ),
        )

    if body.run_id:
        run_dir = UPLOAD_ROOT / body.run_id
    else:
        run_dir = RAW_DATA_DIR

    if not run_dir.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Run/data folder not found: {run_dir}",
        )

    approved_mapping_file = run_dir / "approved_support_type_mappings.json"

    approved_mapping_file.write_text(
        json.dumps(
            {
                "person_id": body.person_id,
                "concept": body.concept,
                "rules": approved_rules,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    log_step(f"Saved approved mapping file: {approved_mapping_file}")
    log_step("STEP 6: Running SupportType transformer")

    try:
        transformed_output = transform_support_type(
            personal_id=body.person_id,
            data_dir=run_dir,
            mappings=approved_rules,
        )
    except TypeError as error:
        raise HTTPException(
            status_code=500,
            detail=(
                "transform_support_type() must accept personal_id, data_dir, and mappings. "
                f"Original error: {error}"
            ),
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))

    output = to_jsonable(transformed_output)

    log_step(f"STEP 7: Transformer finished with {len(output)} result(s)")
    log_step("STEP 8: Returning final validated output")

    return {
        "status": "completed",
        "concept": body.concept,
        "person_id": body.person_id,
        "run_id": body.run_id,
        "message": "Mappings submitted. Transformer executed remaining pipeline steps.",
        "steps_executed": [
            "mapping rules approved",
            "frontend mappings converted into transformer rules",
            "transformer applied mappings",
            "Pydantic validation executed",
            "provenance attached",
            "final SupportType objects returned",
        ],
        "approved_rules": approved_rules,
        "output": output,
    }
