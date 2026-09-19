from pydantic import BaseModel


class ResearchRequest(BaseModel):
    target: str
    task: str


class ResearchResponse(BaseModel):
    run_id: str
    status: str
