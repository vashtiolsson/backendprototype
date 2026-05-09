import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.transform.support_type import transform_support_type
from src.transform.amount import transform_amount
from src.transform.period import transform_period
from src.transform.status import transform_status
from src.transform.occupation import transform_occupation
from src.transform.person import transform_person

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RequestBody(BaseModel):
    category: str


class TransformRequest(BaseModel):
    concept: str
    person_id: str = "20000421-1234"


@app.get("/")
def root():
    return {"status": "NEW BACKEND IS LIVE"}


@app.post("/api/test-pipeline")
def test_pipeline(body: RequestBody):
    print("TEST PIPELINE CALLED")
    print("CATEGORY:", body.category)

    person_id = "20000421-1234"

    support_types = transform_support_type(person_id)
    amounts = transform_amount(person_id)
    periods = transform_period(person_id)
    statuses = transform_status(person_id)
    occupations = transform_occupation(person_id)
    person = transform_person(person_id)

    return {
        "output": {
            "category": body.category,
            "person_id": person_id,
            "person": person.model_dump() if hasattr(person, "model_dump") else person,
            "support_type": [item.model_dump() for item in support_types],
            "amount": [item.model_dump() for item in amounts],
            "time_period": [item.model_dump() for item in periods],
            "status": [item.model_dump() for item in statuses],
            "occupation": [item.model_dump() for item in occupations],
        }
    }

CONCEPT_MODULES = {
    "support-type": {
        "transform": "src.transform.support_type",
        "reasoner": "src.reasoner.support_type_reasoner",
        "mapping": "src.mappings.support_type",  
        "model": "src.models.support_type",

    },

    "amount": {
        "transform": "src.transform.amount",
        "reasoner": "src.reasoner.amount",
        "mapping": "src.mappings.amount",
        "model": "src.models.amount",


    },

    "time-period": {
        "transform": "src.transform.period",
        "reasoner": "src.reasoner.period",
        "mapping": "src.mappings.period",
        "model": "src.models.period",

    },

    "status": {
        "transform": "src.transform.status",
        "reasoner": "src.reasoner.status",
        "mapping": "src.mappings.status",
        "model": "src.models.status",

    },

    "occupation": {
        "transform": "src.transform.occupation",
        "reasoner": "src.reasoner.occupation",
        "mapping": "src.mappings.occupation",
        "model": "src.models.occupation",

    },

    "person": {
        "transform": "src.transform.person",
        "reasoner": "src.reasoner.person",
        "mapping": "src.mappings.person",
        "model": "src.models.person",
    },
}


@app.post("/api/run-{concept_kebab}-{stage_key}-file")
def run_concept_stage_file(concept_kebab: str, stage_key: str):

    if concept_kebab not in CONCEPT_MODULES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown concept: {concept_kebab}"
        )

    concept_stages = CONCEPT_MODULES[concept_kebab]

    if stage_key not in concept_stages:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown stage '{stage_key}' for concept '{concept_kebab}'"
        )

    module = concept_stages[stage_key]

    try:
        backend_root = Path(__file__).resolve().parent

        completed = subprocess.run(
            [sys.executable, "-m", module],
            cwd=backend_root,
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
            detail=f"{concept_kebab} {stage_key} took too long to run."
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )