from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.data.csn_record import CSN_RECORD
from src.logic.engine import register_org_data, run_pipeline

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class PipelineRequest(BaseModel):
    category: str


@app.get("/")
def root():
    return {"status": "API is running"}


@app.post("/api/test-pipeline")
def test_pipeline(body: PipelineRequest):
    register_org_data("CSN", CSN_RECORD)
    result = run_pipeline(body.category)
    return {"output": result}
