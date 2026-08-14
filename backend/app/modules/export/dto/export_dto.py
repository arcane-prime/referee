from pydantic import BaseModel, Field


class ExportInfoDto(BaseModel):
    paper_id: str
    revision: int
    available_revisions: list[int] = Field(default_factory=list)
    detected_style: str
    available_styles: list[str] = Field(default_factory=list)
