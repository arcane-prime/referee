from datetime import datetime

from pydantic import BaseModel, Field


class UploadedPaperDto(BaseModel):
    paper_id: str = Field(examples=["paper_9f2c1ab34de7"])
    filename: str = Field(examples=["attention-is-all-you-need.pdf"])
    size_bytes: int = Field(examples=[1048576])
    uploaded_at: datetime


# Notes
#
# There is no request DTO for upload because the payload is a multipart file,
# not a JSON body. Validation of that file belongs to the provider.
#
# `paper_id` is the only field the frontend needs to keep. Everything else is
# echoed back so the upload screen can confirm what it received without a
# second round trip.
