import asyncio

from fastapi import APIRouter, Depends, Query, status

from app.core.config import get_settings
from app.core.dependencies import get_library_provider
from app.core.exceptions import SearchUnavailableError
from app.core.library_provider import LibraryProvider
from app.domain.library import Reference
from app.modules.extraction.api.dependencies import (
    get_extraction_provider,
    get_parser_backend,
)
from app.modules.extraction.dto.extraction_dto import (
    ExtractionResultDto,
    VerificationDto,
)
from app.modules.extraction.provider.extraction_provider import ExtractionProvider
from app.modules.extraction.provider.parser_backend import ParserBackend
from app.modules.resolution.api.dependencies import (
    get_resolution_provider,
    get_search_backend,
)
from app.modules.resolution.provider.resolution_provider import ResolutionProvider
from app.modules.resolution.provider.search_backend import SearchBackend

router = APIRouter(tags=["extraction"])


@router.post(
    "/papers/{paper_id}/extract",
    response_model=ExtractionResultDto,
    status_code=status.HTTP_200_OK,
    summary="Extract a stored PDF and check its references against real databases",
)
async def extract_paper(
    paper_id: str,
    use_cached_tei: bool = Query(
        default=False,
        description="Re-run the translation against TEI already on disk, without calling the parser.",
    ),
    extraction: ExtractionProvider = Depends(get_extraction_provider),
    resolution: ResolutionProvider = Depends(get_resolution_provider),
    search: SearchBackend = Depends(get_search_backend),
    library: LibraryProvider = Depends(get_library_provider),
) -> ExtractionResultDto:
    result = await extraction.extract(paper_id=paper_id, use_cached_tei=use_cached_tei)

    references, verification = await verify(
        resolution=resolution,
        search_name=search.name,
        raw_references=extraction.load_references(paper_id),
    )

    if references is None:
        library.merge(paper_id, result.references)
        return result.model_copy(update={"verification": verification})

    library.merge(paper_id, references)
    return result.model_copy(
        update={"references": references, "verification": verification}
    )


async def verify(
    resolution: ResolutionProvider,
    search_name: str,
    raw_references: list,
) -> tuple[list[Reference] | None, VerificationDto]:
    if not raw_references:
        return None, VerificationDto(
            attempted=False,
            succeeded=False,
            message="This paper has no references to check.",
        )

    budget = get_settings().verification_budget_seconds

    try:
        references = await asyncio.wait_for(
            resolution.resolve_all(raw_references), timeout=budget
        )
    except SearchUnavailableError as exc:
        return None, VerificationDto(
            attempted=True,
            succeeded=False,
            search_api=search_name,
            message=(
                f"The paper was extracted, but its references could not be checked "
                f"against the literature databases. {exc.detail}"
            ),
        )
    except asyncio.TimeoutError:
        return None, VerificationDto(
            attempted=True,
            succeeded=False,
            search_api=search_name,
            message=(
                f"The paper was extracted, but checking its {len(raw_references)} "
                f"references took longer than {budget:.0f}s and was stopped. The "
                f"literature databases are rate limiting this client right now."
            ),
        )

    return references, VerificationDto(
        attempted=True,
        succeeded=True,
        search_api=search_name,
        resolved=sum(1 for r in references if r.resolution.status == "resolved"),
        ambiguous=sum(1 for r in references if r.resolution.status == "ambiguous"),
        unresolved=sum(1 for r in references if r.resolution.status == "unresolved"),
        with_abstract=sum(1 for r in references if r.has_abstract),
        with_doi=sum(1 for r in references if r.doi),
    )


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
# Extraction and verification run together because checking references against
# the literature is part of producing a parse, not a separate thing to ask for.
# There is no decision to offer the user: nobody wants their references left
# unchecked, and a control with one sensible answer should not exist.
#
# Composing the two modules happens here in the route rather than inside either
# provider. Extraction must not depend on resolution, since resolution already
# depends on extraction and the cycle would be real rather than stylistic. The
# route is the layer whose job is composition.
#
# A verification failure never fails the request. The parse is genuinely useful
# on its own, and losing it because a public database was out of quota would be
# a poor trade. The response says plainly that the paper was extracted but not
# verified, so the caller can tell "we could not check" apart from "we checked
# and found nothing" - which is the difference between an outage and forty
# missing references.
#
# References come back as Reference objects either way. When verification did
# not run they are simply unresolved, so the caller has one list to render
# rather than two shapes to reconcile.
#
# Both paths write the library, including the one where verification failed.
# An unresolved reference still belongs in it: the agent may not cite it, since
# can_be_cited_by_the_agent is false without an external id, but stage 4 needs
# to know the reference exists in order to say so. Writing only on success
# would leave a rate limited paper with no library at all, which is a different
# and less honest failure than a library full of unresolved entries.
#
# The whole verification step runs under a single time budget. Without one, a
# paper with seventy references discovers that a database is throttling it
# seventy separate times, each with its own backoff, and an extraction that
# should take under a minute grinds on for many. The budget converts that into
# a bounded wait followed by an honest "not verified", which is a far better
# outcome than a page that appears to hang.
#
# It is enforced here rather than per request inside the clients because the
# thing worth bounding is what the user is waiting for. Individual lookups
# already have their own timeouts; this caps the sum.
#
# parser/status sits at /parser/status rather than under /papers because a
# literal segment inside a {paper_id} namespace is a collision waiting to
# happen: the moment a GET /papers/{paper_id} exists, "parser" becomes a paper
# id that shadows it.
