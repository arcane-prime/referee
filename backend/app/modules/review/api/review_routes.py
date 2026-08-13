from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status

from app.domain.document import Document
from app.domain.library import Reference
from app.domain.review import Finding
from app.modules.extraction.api.dependencies import get_extraction_provider
from app.modules.extraction.provider.extraction_provider import ExtractionProvider
from app.modules.resolution.api.dependencies import get_resolution_provider
from app.modules.resolution.provider.resolution_provider import ResolutionProvider
from app.modules.review.api.dependencies import get_llm_backend, get_review_provider
from app.modules.review.dto.review_dto import ReviewResultDto, ReviewSummaryDto
from app.modules.review.provider.llm_backend import LlmBackend
from app.modules.review.provider.review_provider import ReviewProvider
from app.modules.review.provider.sentence_provider import SentenceProvider

router = APIRouter(tags=["review"])


@router.post(
    "/papers/{paper_id}/review",
    response_model=ReviewResultDto,
    status_code=status.HTTP_200_OK,
    summary="Review a paper's claims against its cited sources",
)
async def review_paper(
    paper_id: str,
    check_support: bool = Query(default=True),
    find_uncited_claims: bool = Query(default=True),
    find_missing_work: bool = Query(default=True),
    extraction: ExtractionProvider = Depends(get_extraction_provider),
    resolution: ResolutionProvider = Depends(get_resolution_provider),
    review: ReviewProvider = Depends(get_review_provider),
    llm: LlmBackend = Depends(get_llm_backend),
) -> ReviewResultDto:
    document = extraction.load_document(paper_id)
    raw_references = extraction.load_references(paper_id)

    references: list[Reference] = []
    if check_support:
        references = await resolution.resolve_all(raw_references)

    findings = await review.review(
        document=document,
        references=references,
        check_support=check_support,
        find_uncited_claims=find_uncited_claims,
        find_missing_work=find_missing_work,
    )

    return ReviewResultDto(
        paper_id=paper_id,
        reviewed_at=datetime.now(timezone.utc),
        model=llm.name,
        findings=findings,
        summary=summarise(document, references, findings),
    )


def summarise(
    document: Document,
    references: list[Reference],
    findings: list[Finding],
) -> ReviewSummaryDto:
    sentences = SentenceProvider().for_document(document)
    cited = [sentence for sentence in sentences if sentence.is_cited]
    with_abstract = {
        reference.id for reference in references if reference.has_abstract
    }

    checked = sum(
        1
        for sentence in cited
        for ref_id in sentence.ref_ids
        if ref_id in with_abstract
    )

    return ReviewSummaryDto(
        sentences_examined=len(sentences),
        claims_with_citations=len(cited),
        citations_checked=checked,
        references_without_abstract=sum(
            1 for reference in references if not reference.has_abstract
        ),
        findings_total=len(findings),
        unsupported_claims=sum(
            1 for finding in findings if finding.kind == "unsupported_claim"
        ),
        missing_citations=sum(
            1 for finding in findings if finding.kind == "missing_citation"
        ),
    )


# Notes
#
# Review composes the two stages before it: the document comes from the stored
# extraction, the references are resolved so their abstracts are available. It
# is the only route that touches three modules, which is inherent rather than
# accidental, since reviewing a claim requires both the claim and the source.
#
# The document is read from rev_0.json rather than re-parsed, because that file
# is the extraction the user actually saw. Re-deriving it would risk reviewing
# a slightly different document from the one on screen.
#
# Resolution is re-run rather than cached in memory, and costs nothing after
# the first time thanks to the HTTP cache, so the review always sees current
# abstracts without a persistence layer that does not exist yet.
#
# It is skipped entirely when check_support is off, rather than run and
# ignored. Resolving forty references against a database that is out of quota
# costs a long wait for results nothing will read, and the uncited-claim pass
# needs no external service at all.
#
# The two passes are separately switchable through query parameters. Support
# checking works from the paper's own bibliography alone, so when the search
# quota is spent, find_missing_work=false still produces a complete and honest
# review rather than a failure.
#
# A 409 comes back when the paper was never extracted, for the same reason as
# in resolution: the paper exists, the caller asked for a step out of order.