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
