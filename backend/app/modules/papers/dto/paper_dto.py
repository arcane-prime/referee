from datetime import datetime

from pydantic import BaseModel, Field


class UploadedPaperDto(BaseModel):
    paper_id: str = Field(examples=["paper_9f2c1ab34de7"])
    filename: str = Field(examples=["attention-is-all-you-need.pdf"])
    size_bytes: int = Field(examples=[1048576])
    uploaded_at: datetime
