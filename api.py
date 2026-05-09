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


@app.post("/api/run-transform")
def run_transform(body: TransformRequest):
    print("RUN TRANSFORM CALLED")
    print("CONCEPT:", body.concept)
    print("PERSON ID:", body.person_id)

    runners = {
        "SupportType": transform_support_type,
        "Amount": transform_amount,
        "TimePeriod": transform_period,
        "Status": transform_status,
        "Occupation": transform_occupation,
        "Person": transform_person,
    }

    if body.concept not in runners:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown concept: {body.concept}"
        )

    result = runners[body.concept](body.person_id)

    if isinstance(result, list):
        output = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in result
        ]
    else:
        output = result.model_dump() if hasattr(result, "model_dump") else result

    return {
        "concept": body.concept,
        "person_id": body.person_id,
        "stage": "transform",
        "output": output,
    }

@app.post("/api/run-support-type-transform-file")
def run_support_type_transform_file():
    try:
        backend_root = Path(__file__).resolve().parent

        completed = subprocess.run(
            [sys.executable, "-m", "src.transform.support_type"],
            cwd=backend_root,
            capture_output=True,
            text=True,
            timeout=30,
        )

        return {
            "command": "python -m src.transform.support_type",
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=504,
            detail="SupportType transformer took too long to run."
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )