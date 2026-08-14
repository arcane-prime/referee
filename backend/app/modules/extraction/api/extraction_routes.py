from fastapi import APIRouter, Depends, Query, status

from app.modules.extraction.api.dependencies import (
    get_extraction_provider,
    get_parser_backend,
)
from app.modules.extraction.dto.extraction_dto import ExtractionResultDto
from app.modules.extraction.provider.extraction_provider import ExtractionProvider
from app.modules.extraction.provider.parser_backend import ParserBackend

router = APIRouter(tags=["extraction"])


@router.post(
    "/papers/{paper_id}/extract",
    response_model=ExtractionResultDto,
    status_code=status.HTTP_200_OK,
    summary="Parse a stored PDF into a structured document with citation nodes",
)
async def extract_paper(
    paper_id: str,
    use_cached_tei: bool = Query(
        default=False,
        description="Re-run the translation against TEI already on disk, without calling the parser.",
    ),
    extraction: ExtractionProvider = Depends(get_extraction_provider),
) -> ExtractionResultDto:
    return await extraction.extract(paper_id=paper_id, use_cached_tei=use_cached_tei)


@router.get(
    "/parser/status",
    tags=["system"],
    summary="Report whether the parser backend is reachable",
)
async def parser_status(
    parser: ParserBackend = Depends(get_parser_backend),
) -> dict[str, object]:
    return {"parser": parser.name, "alive": await parser.is_alive()}
