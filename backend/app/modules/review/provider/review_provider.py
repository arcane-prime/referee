import asyncio

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

            for sentence, suggestions in await asyncio.gather(
                *(run(sentence) for sentence in claims)
            ):
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


# Notes
#
# The orchestrator owns the sequence and the anchoring, and contains no
# judgement of its own.
#
# Findings are only ever emitted for sentences that came out of
# SentenceProvider, so every one carries a real block id, sentence index and
# character span. The model chose which sentence, never what the sentence says.
#
# is_grounded is enforced as the last step of both passes, and it is the
# brief's hardest rule made mechanical. An unsupported-claim finding survives
# only if some evidence carries a verified quote; a missing-citation finding
# survives only if some suggestion carries a real identifier. Anything else is
# discarded rather than shown, however confident the model was.
#
# Only problem grades become findings. A citation the source supports is the
# normal case and reporting it would bury the few that matter in noise.
#
# Evidence is grouped per sentence rather than per reference, because a
# sentence citing three works is one claim to a reader, not three findings.
# Severity follows the worst grade among them, since a contradiction alongside
# two partial supports is still a contradiction.
#
# References with no abstract are skipped before any model call. There is
# nothing to check against, and judging from a title is the behaviour the whole
# design exists to prevent. Their absence is reported in the summary instead.
#
# The passes are independent and separately switchable, and they need
# progressively more of the outside world:
#
#   uncited claims   the document alone, plus the model
#   support checks   the paper's own bibliography, resolved with abstracts
#   missing work     a live literature search
#
# That ordering is deliberate. A claim carrying no citation is detectable with
# nothing but the paper's text, so the review degrades in useful steps rather
# than failing outright when an external service is unavailable.
#
# When search is available an uncited claim is upgraded to a missing_citation
# carrying real candidates; when it is not, the same sentence is still reported
# as an uncited claim. The finding never pretends to know which work would
# support it, so the honest weaker statement survives without inventing the
# stronger one.
#
# Abstracts and captions are excluded from the uncited-claim pass entirely.
# Academic convention is that abstracts do not carry citations, so every
# factual sentence in one looks like a missing citation and none of them are.
# On the first real paper this produced four findings out of twelve that an
# author would rightly dismiss, which is the fastest way to teach them to
# ignore the other eight as well.
#
# The exclusion is by block kind rather than by prompting, because it is a
# property of the document rather than a judgement. Those blocks are still
# checked by the support pass when they do carry a citation; it is only the
# expectation of a citation that does not apply.
#
# Claims investigated for missing work are capped. A long paper has many
# uncited claims, each costing a search and a judgement, and a reviewer that
# returns forty suggestions is one nobody reads.
