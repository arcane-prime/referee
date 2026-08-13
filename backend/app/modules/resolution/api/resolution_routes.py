from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status

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
) -> ResolutionResultDto:
    raw_references = extraction.load_references(paper_id)
    references = await resolution.resolve_all(raw_references)

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


# Notes
#
# Resolution is an explicit call, like extraction. Uploading stores a file,
# extracting parses it, resolving checks it against the world. Each step is
# something the user asks for, and each can be re-run on its own.
#
# The route reaches into extraction only through load_references, which is a
# read-only derivation from the TEI already on disk. That is the one dependency
# between feature modules in this codebase and it is a real one: resolution
# operates on extraction's output by definition. Keeping it to a single narrow
# method, rather than letting resolution parse TEI itself, means there is still
# exactly one implementation of "what are this paper's references".
#
# A 409 comes back if the paper was never extracted, rather than a 404. The
# paper exists; the caller just asked for a step out of order.
#
# The summary is computed here from the references being returned, so it cannot
# disagree with them.