import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

from app.core.config import get_settings
from app.core.dependencies import get_library_provider
from app.core.exceptions import SearchUnavailableError
from app.core.library_provider import LibraryProvider
from app.domain.library import Reference
from app.modules.extraction.api.dependencies import get_extraction_provider
from app.modules.extraction.provider.extraction_provider import ExtractionProvider
from app.modules.resolution.api.dependencies import (
    get_abstract_backend,
    get_resolution_provider,
    get_search_backend,
)
from app.modules.resolution.dto.resolution_dto import (
    ResolutionResultDto,
    ResolutionSummaryDto,
)
from app.modules.resolution.provider.resolution_provider import ResolutionProvider
from app.modules.resolution.provider.search_backend import AbstractBackend, SearchBackend

router = APIRouter(tags=["resolution"])


@router.post(
    "/papers/{paper_id}/resolve",
    response_model=ResolutionResultDto,
    status_code=status.HTTP_200_OK,
    summary="Match extracted references against real academic databases",
)
async def resolve_paper(
    paper_id: str,
    extraction: ExtractionProvider = Depends(get_extraction_provider),
    resolution: ResolutionProvider = Depends(get_resolution_provider),
    search: SearchBackend = Depends(get_search_backend),
    abstracts: AbstractBackend = Depends(get_abstract_backend),
    library: LibraryProvider = Depends(get_library_provider),
) -> ResolutionResultDto:
    raw_references = extraction.load_references(paper_id)
    budget = get_settings().verification_budget_seconds

    try:
        references = await asyncio.wait_for(
            resolution.resolve_all(raw_references), timeout=budget
        )
    except asyncio.TimeoutError as exc:
        raise SearchUnavailableError(
            f"Checking these {len(raw_references)} references took longer than "
            f"{budget:.0f}s and was stopped. The literature databases are rate "
            f"limiting this client right now. The parse is unaffected."
        ) from exc

    library.merge(paper_id, references)

    return ResolutionResultDto(
        paper_id=paper_id,
        resolved_at=datetime.now(timezone.utc),
        search_api=search.name,
        abstract_api=abstracts.name,
        references=references,
        summary=summarise(references),
    )


def summarise(references: list[Reference]) -> ResolutionSummaryDto:
    return ResolutionSummaryDto(
        total=len(references),
        resolved=sum(1 for ref in references if ref.resolution.status == "resolved"),
        ambiguous=sum(1 for ref in references if ref.resolution.status == "ambiguous"),
        unresolved=sum(1 for ref in references if ref.resolution.status == "unresolved"),
        with_abstract=sum(1 for ref in references if ref.has_abstract),
        with_doi=sum(1 for ref in references if ref.doi),
    )
