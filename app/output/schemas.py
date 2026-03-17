from pydantic import BaseModel, Field


class GeneralReply(BaseModel):
    content: str
    confidence: float = Field(ge=0, le=1, default=1.0)


class ResearchReport(BaseModel):
    title: str
    summary: str
    sources: list[str] = []
    findings: list[str]


class CodeReview(BaseModel):
    file: str
    issues: list[dict] = []
    suggestions: list[str] = []
    overall_quality: str = "good"
