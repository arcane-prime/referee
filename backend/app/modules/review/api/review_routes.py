from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import get_library_provider
from app.core.library_provider import LibraryProvider
from app.domain.document import Document
from app.domain.library import Reference
from app.domain.review import Finding
from app.modules.extraction.api.dependencies import get_extraction_provider
from app.modules.extraction.provider.extraction_provider import ExtractionProvider
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
    revision: int | None = Query(default=None),
    check_support: bool = Query(default=True),
    find_uncited_claims: bool = Query(default=True),
    find_missing_work: bool = Query(default=True),
    extraction: ExtractionProvider = Depends(get_extraction_provider),
    library: LibraryProvider = Depends(get_library_provider),
    review: ReviewProvider = Depends(get_review_provider),
    llm: LlmBackend = Depends(get_llm_backend),
) -> ReviewResultDto:
    document, number = extraction.load_document(paper_id, revision)

    references: list[Reference] = []
    if check_support:
        references = library.load(paper_id).references

    findings = await review.review(
        document=document,
        references=references,
        check_support=check_support,
        find_uncited_claims=find_uncited_claims,
        find_missing_work=find_missing_work,
    )

    return ReviewResultDto(
        paper_id=paper_id,
        revision=number,
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
