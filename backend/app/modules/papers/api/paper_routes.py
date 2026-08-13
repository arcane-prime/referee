from fastapi import APIRouter, Depends, File, UploadFile, status

from app.modules.papers.api.dependencies import get_paper_provider
from app.modules.papers.dto.paper_dto import UploadedPaperDto
from app.modules.papers.provider.paper_provider import PaperProvider

router = APIRouter(prefix="/papers", tags=["papers"])


@router.post(
    "",
    response_model=UploadedPaperDto,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a paper as PDF",
)
async def upload_paper(
    file: UploadFile = File(...),
    provider: PaperProvider = Depends(get_paper_provider),
) -> UploadedPaperDto:
    content = await file.read()
    return provider.create_from_upload(
        filename=file.filename or "upload.pdf",
        content=content,
    )


# Notes
#
# The route does three things and no more: read the multipart body, hand the
# bytes to the provider, return the DTO. Every rule about what makes an upload
# acceptable lives in the provider, so those rules can be tested without an
# HTTP client.
#
# Failures surface as domain exceptions caught by the handler in core, which is
# why there is no try/except and no HTTPException here.
#
# Uploading is currently synchronous and returns as soon as the file is on
# disk. Once parsing is attached, this call will take as long as GROBID does,
# and the decision between blocking here or returning a pending status is made
# at that point.
