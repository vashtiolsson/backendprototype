from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.transform.support_type import transform_support_type

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class RequestBody(BaseModel):
    category: str

@app.get("/")
def root():
    return {"status": "NEW BACKEND IS LIVE"}

@app.post("/api/test-pipeline")
def test_pipeline(body: RequestBody):
    print("TEST PIPELINE CALLED")
    print("CATEGORY:", body.category)

    support_types = transform_support_type("20000421-1234")
    print("SUPPORT TYPES:", support_types)

    return {
        "output": {
            "category": body.category,
            "person_id": "20000421-1234",
            "support_type": [item.model_dump() for item in support_types],
        }
    }