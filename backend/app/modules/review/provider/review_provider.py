import asyncio

from app.core.exceptions import SearchUnavailableError
from app.domain.document import Document
from app.domain.library import Reference
from app.domain.review import Evidence, Finding, Sentence
from app.modules.review.provider.claim_provider import ClaimProvider
from app.modules.review.provider.discovery_provider import (
    MAX_CLAIMS_INVESTIGATED,
    DiscoveryProvider,
)
from app.modules.review.provider.sentence_provider import SentenceProvider
from app.modules.review.provider.support_provider import SupportProvider

PROBLEM_GRADES = {"not_supported", "partially_supports"}

NON_CITING_BLOCK_KINDS = {"abstract", "caption", "heading", "formula"}

DISCOVERY_BUDGET_SECONDS = 25.0


class ReviewProvider:
    def __init__(
        self,
        sentences: SentenceProvider,
        claims: ClaimProvider,
        support: SupportProvider,
        discovery: DiscoveryProvider | None = None,
        concurrency: int = 4,
    ) -> None:
        self._sentences = sentences
        self._claims = claims
        self._support = support
        self._discovery = discovery
        self._concurrency = max(1, concurrency)

    async def review(
        self,
        document: Document,
        references: list[Reference],
        check_support: bool = True,
        find_uncited_claims: bool = True,
        find_missing_work: bool = True,
    ) -> list[Finding]:
        sentences = self._sentences.for_document(document)
        by_id = {reference.id: reference for reference in references}

        findings: list[Finding] = []
        counter = 0

        if check_support:
            for finding in await self._check_support(sentences, by_id):
                counter += 1
                findings.append(finding.model_copy(update={"id": f"f_{counter:04d}"}))

        if find_uncited_claims:
            for finding in await self._find_uncited_claims(
                document, sentences, references, find_missing_work
            ):
                counter += 1
                findings.append(finding.model_copy(update={"id": f"f_{counter:04d}"}))

        return findings

    async def _check_support(
        self,
        sentences: list[Sentence],
        by_id: dict[str, Reference],
    ) -> list[Finding]:
        checkable = [
            (sentence, reference)
            for sentence in sentences
            if sentence.is_cited
            for reference in (by_id.get(ref_id) for ref_id in sentence.ref_ids)
            if reference is not None and reference.has_abstract
        ]
        if not checkable:
            return []

        limiter = asyncio.Semaphore(self._concurrency)

        async def run(pair) -> tuple[Sentence, Evidence | None]:
            sentence, reference = pair
            async with limiter:
                return sentence, await self._support.check(sentence, reference)

        results = await asyncio.gather(*(run(pair) for pair in checkable))

        grouped: dict[tuple[str, int], list[Evidence]] = {}
        anchors: dict[tuple[str, int], Sentence] = {}
        for sentence, evidence in results:
            if evidence is None:
                continue
            key = (sentence.block_id, sentence.index)
            grouped.setdefault(key, []).append(evidence)
            anchors[key] = sentence

        findings: list[Finding] = []
        for key, evidence_list in grouped.items():
            if not any(item.grade in PROBLEM_GRADES for item in evidence_list):
                continue

            sentence = anchors[key]
            worst = self._worst(evidence_list)

            findings.append(
                Finding(
                    id="pending",
                    kind="unsupported_claim",
                    severity="high" if worst == "not_supported" else "medium",
                    block_id=sentence.block_id,
                    sentence_index=sentence.index,
                    start=sentence.start,
                    end=sentence.end,
                    sentence=sentence.text,
                    message=self._support_message(worst),
                    evidence=evidence_list,
                )
            )

        return [finding for finding in findings if finding.is_grounded]

    @staticmethod
    def _blocks_that_never_cite(document: Document) -> set[str]:
        return {
            block.id
            for block in document.blocks()
            if block.kind in NON_CITING_BLOCK_KINDS
        }

    async def _find_uncited_claims(
        self,
        document: Document,
        sentences: list[Sentence],
        references: list[Reference],
        find_missing_work: bool,
    ) -> list[Finding]:
        claims = await self._claims.find_uncited_claims(
            sentences,
            limit=MAX_CLAIMS_INVESTIGATED,
            skip_block_ids=self._blocks_that_never_cite(document),
        )
        if not claims:
            return []
        suggestions_by_key: dict[tuple[str, int], list] = {}

        if find_missing_work and self._discovery is not None:
            already_cited = DiscoveryProvider.already_cited_identifiers(references)
            limiter = asyncio.Semaphore(self._concurrency)

            async def run(sentence: Sentence):
                async with limiter:
                    return sentence, await self._discovery.find_missing_work(
                        sentence, already_cited
                    )

            try:
                found = await asyncio.wait_for(
                    asyncio.gather(*(run(sentence) for sentence in claims)),
                    timeout=DISCOVERY_BUDGET_SECONDS,
                )
            except (asyncio.TimeoutError, SearchUnavailableError):
                found = []

            for sentence, suggestions in found:
                if suggestions:
                    suggestions_by_key[(sentence.block_id, sentence.index)] = suggestions

        findings: list[Finding] = []
        for sentence in claims:
            suggestions = suggestions_by_key.get((sentence.block_id, sentence.index), [])

            findings.append(
                Finding(
                    id="pending",
                    kind="missing_citation" if suggestions else "uncited_claim",
                    severity="medium" if suggestions else "low",
                    block_id=sentence.block_id,
                    sentence_index=sentence.index,
                    start=sentence.start,
                    end=sentence.end,
                    sentence=sentence.text,
                    message=(
                        f"This claim carries no citation. "
                        f"{len(suggestions)} relevant work(s) were found."
                        if suggestions
                        else "This states a factual claim but carries no citation."
                    ),
                    suggested_sources=suggestions,
                )
            )

        return [finding for finding in findings if finding.is_grounded]

    @staticmethod
    def _worst(evidence: list[Evidence]) -> str:
        if any(item.grade == "not_supported" for item in evidence):
            return "not_supported"
        return "partially_supports"

    @staticmethod
    def _support_message(grade: str) -> str:
        if grade == "not_supported":
            return "The cited source appears to contradict this claim."
        return "The cited source only partially supports this claim."
