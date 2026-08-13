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
    summary="Extract a stored PDF into a structured document",
)
async def extract_paper(
    paper_id: str,
    use_cached_tei: bool = Query(
        default=False,
        description="Re-run the translation against TEI already on disk, without calling the parser.",
    ),
    provider: ExtractionProvider = Depends(get_extraction_provider),
) -> ExtractionResultDto:
    return await provider.extract(paper_id=paper_id, use_cached_tei=use_cached_tei)


@router.get(
    "/parser/status",
    tags=["system"],
    summary="Report whether the parser backend is reachable",
)
async def parser_status(
    parser: ParserBackend = Depends(get_parser_backend),
) -> dict[str, object]:
    return {"parser": parser.name, "alive": await parser.is_alive()}


# Notes
#
# Extraction is an explicit call, not a side effect of upload. Uploading stores
# a file and nothing more; parsing happens when the user asks for it. That also
# means a paper can be re-extracted after a parser change without re-uploading.
#
# The route is thin on purpose: it resolves a provider and awaits it. Failures
# surface as domain exceptions handled centrally, which is why there is no
# try/except and no HTTPException here.
#
# parser/status exists because the most common failure during development is
# "the parser is not running", and that should be answerable without uploading
# a PDF and waiting for a timeout to explain it.
#
# It sits at /parser/status rather than under /papers because a literal segment
# inside a {paper_id} namespace is a collision waiting to happen: the moment a
# GET /papers/{paper_id} exists, "parser" becomes a paper id that shadows it.
