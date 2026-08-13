import asyncio

from app.domain.csl import CSLItem
from app.domain.document import Block, CiteNode, Document, Section, TextRun
from app.domain.library import ExternalIds, Reference, Resolution
from app.domain.review import Sentence
from app.modules.review.provider.claim_provider import ClaimProvider
from app.modules.review.provider.review_provider import ReviewProvider
from app.modules.review.provider.sentence_provider import SentenceProvider
from app.modules.review.provider.stub_llm_provider import StubLlmProvider
from app.modules.review.provider.support_provider import (
    SupportProvider,
    quote_is_verbatim,
)

ABSTRACT = (
    "We propose the Transformer, a model architecture relying entirely on an "
    "attention mechanism to draw global dependencies between input and output. "
    "Experiments on two machine translation tasks show these models to be "
    "superior in quality while being more parallelizable."
)


def block(*inlines, block_id="s0.p0"):
    return Block(id=block_id, kind="paragraph", inlines=list(inlines))


def resolved_reference(ref_id="ref_1", abstract=ABSTRACT):
    return Reference(
        id=ref_id,
        raw="A printed reference.",
        parsed=CSLItem(id=ref_id, title="Attention Is All You Need"),
        resolution=Resolution(
            status="resolved",
            score=0.95,
            matched=CSLItem(id=ref_id, title="Attention Is All You Need"),
            external_ids=ExternalIds(doi="10.5555/3295222"),
            abstract=abstract,
        ),
    )


def sentence(text, cite_nodes=()):
    return Sentence(
        block_id="s0.p0",
        index=0,
        text=text,
        start=0,
        end=len(text),
        cite_nodes=list(cite_nodes),
    )


class TestSentenceSplitting:
    def test_a_paragraph_splits_into_sentences(self):
        result = SentenceProvider().for_block(
            block(TextRun(text="Transformers are strong. They replaced recurrence."))
        )

        assert [s.text for s in result] == [
            "Transformers are strong.",
            "They replaced recurrence.",
        ]

    def test_a_citation_lands_in_the_sentence_containing_it(self):
        result = SentenceProvider().for_block(
            block(
                TextRun(text="Recurrent networks are established "),
                CiteNode(id="c1", ref_ids=["ref_12"]),
                TextRun(text=". Attention replaced them entirely."),
            )
        )

        assert result[0].ref_ids == ["ref_12"]
        assert result[1].ref_ids == []

    def test_abbreviations_do_not_split_a_sentence(self):
        result = SentenceProvider().for_block(
            block(TextRun(text="Vaswani et al. showed that attention suffices here."))
        )

        assert len(result) == 1

    def test_initials_do_not_split_a_sentence(self):
        result = SentenceProvider().for_block(
            block(TextRun(text="This was shown by J. Smith in later work on models."))
        )

        assert len(result) == 1

    def test_offsets_point_back_at_the_real_prose(self):
        text = "Transformers are strong. They replaced recurrence."
        result = SentenceProvider().for_block(block(TextRun(text=text)))

        for item in result:
            assert text[item.start : item.end].strip() == item.text

    def test_citations_contribute_no_characters_to_offsets(self):
        target = block(
            TextRun(text="Networks are established "),
            CiteNode(id="c1", ref_ids=["ref_12"]),
            TextRun(text=" and widely used."),
        )
        result = SentenceProvider().for_block(target)

        assert result[0].text == target.display_text.strip()

    def test_captions_are_not_reviewed(self):
        document = Document(
            id="d",
            paper_id="p",
            title="T",
            sections=[
                Section(
                    id="s_floats",
                    title="Figures",
                    blocks=[
                        Block(
                            id="s_floats.p0",
                            kind="caption",
                            inlines=[TextRun(text="Figure 1: the model architecture.")],
                        )
                    ],
                )
            ],
        )

        assert SentenceProvider().for_document(document) == []


class TestQuoteVerification:
    def test_a_verbatim_quote_verifies(self):
        assert quote_is_verbatim("relying entirely on an attention mechanism", ABSTRACT)

    def test_whitespace_and_case_differences_still_verify(self):
        assert quote_is_verbatim("Relying   entirely\non an attention mechanism", ABSTRACT)

    def test_a_fabricated_quote_does_not_verify(self):
        assert not quote_is_verbatim(
            "the Transformer achieves 99% accuracy on every benchmark", ABSTRACT
        )

    def test_a_paraphrase_does_not_verify(self):
        assert not quote_is_verbatim(
            "the model uses attention to connect inputs and outputs", ABSTRACT
        )

    def test_a_trivially_short_quote_does_not_verify(self):
        assert not quote_is_verbatim("the", ABSTRACT)

    def test_an_empty_quote_does_not_verify(self):
        assert not quote_is_verbatim("", ABSTRACT)


class TestSupportPass:
    def test_a_real_quote_keeps_the_model_grade(self):
        llm = StubLlmProvider(
            {
                "claim_support": {
                    "quote": "Experiments on two machine translation tasks show these "
                    "models to be superior in quality",
                    "grade": "supports",
                    "note": "Directly stated.",
                }
            }
        )
        evidence = asyncio.run(
            SupportProvider(llm).check(
                sentence("Transformers outperform prior models on translation."),
                resolved_reference(),
            )
        )

        assert evidence.quote_verified is True
        assert evidence.grade == "supports"

    def test_a_fabricated_quote_is_downgraded_whatever_the_model_claimed(self):
        llm = StubLlmProvider(
            {
                "claim_support": {
                    "quote": "the Transformer reaches state of the art on every task",
                    "grade": "supports",
                    "note": "Model asserted this confidently.",
                }
            }
        )
        evidence = asyncio.run(
            SupportProvider(llm).check(
                sentence("Transformers beat everything."), resolved_reference()
            )
        )

        assert evidence.quote_verified is False
        assert evidence.grade == "insufficient_evidence"
        assert "not found verbatim" in evidence.note

    def test_a_reference_without_an_abstract_is_skipped_entirely(self):
        llm = StubLlmProvider()
        evidence = asyncio.run(
            SupportProvider(llm).check(
                sentence("A claim."), resolved_reference(abstract=None)
            )
        )

        assert evidence is None
        assert llm.calls == []

    def test_an_unknown_grade_falls_back_to_insufficient_evidence(self):
        llm = StubLlmProvider(
            {
                "claim_support": {
                    "quote": "relying entirely on an attention mechanism",
                    "grade": "definitely_true",
                    "note": "",
                }
            }
        )
        evidence = asyncio.run(
            SupportProvider(llm).check(sentence("A claim."), resolved_reference())
        )

        assert evidence.grade == "insufficient_evidence"


class TestClaimPass:
    def test_only_sentences_the_model_flagged_are_returned(self):
        llm = StubLlmProvider(
            {
                "uncited_claims": {
                    "claims": [
                        {"index": 0, "needs_citation": True, "reason": "prior work"},
                        {"index": 1, "needs_citation": False, "reason": "own method"},
                    ]
                }
            }
        )
        sentences = [
            sentence("Recurrent networks have long been the state of the art here."),
            sentence("In this paper we propose a new architecture for translation."),
        ]

        flagged = asyncio.run(ClaimProvider(llm).find_uncited_claims(sentences))

        assert len(flagged) == 1
        assert flagged[0].text.startswith("Recurrent networks")

    def test_an_out_of_range_index_is_discarded(self):
        llm = StubLlmProvider(
            {"uncited_claims": {"claims": [{"index": 99, "needs_citation": True, "reason": "x"}]}}
        )
        sentences = [sentence("A claim long enough to be considered by the pass.")]

        assert asyncio.run(ClaimProvider(llm).find_uncited_claims(sentences)) == []

    def test_already_cited_sentences_are_never_considered(self):
        llm = StubLlmProvider()
        cited = sentence(
            "Recurrent networks have long been the state of the art here.",
            [CiteNode(id="c1", ref_ids=["ref_1"])],
        )

        assert asyncio.run(ClaimProvider(llm).find_uncited_claims([cited])) == []
        assert llm.calls == []


class TestReviewOrchestration:
    def build(self, llm):
        return ReviewProvider(
            sentences=SentenceProvider(),
            claims=ClaimProvider(llm),
            support=SupportProvider(llm),
            discovery=None,
        )

    def document_citing(self, ref_id="ref_1"):
        return Document(
            id="d",
            paper_id="p",
            title="T",
            sections=[
                Section(
                    id="s0",
                    title="Intro",
                    blocks=[
                        block(
                            TextRun(text="Transformers are superior for translation "),
                            CiteNode(id="c1", ref_ids=[ref_id]),
                            TextRun(text="."),
                        )
                    ],
                )
            ],
        )

    def test_a_contradicted_claim_becomes_a_high_severity_finding(self):
        llm = StubLlmProvider(
            {
                "claim_support": {
                    "quote": "Experiments on two machine translation tasks show these "
                    "models to be superior in quality",
                    "grade": "not_supported",
                    "note": "Contradicts.",
                }
            }
        )
        findings = asyncio.run(
            self.build(llm).review(
                self.document_citing(), [resolved_reference()], find_missing_work=False
            )
        )

        assert len(findings) == 1
        assert findings[0].kind == "unsupported_claim"
        assert findings[0].severity == "high"
        assert findings[0].block_id == "s0.p0"

    def test_a_supported_claim_produces_no_finding(self):
        llm = StubLlmProvider(
            {
                "claim_support": {
                    "quote": "relying entirely on an attention mechanism",
                    "grade": "supports",
                    "note": "Fine.",
                }
            }
        )
        findings = asyncio.run(
            self.build(llm).review(
                self.document_citing(), [resolved_reference()], find_missing_work=False
            )
        )

        assert findings == []

    def test_a_finding_built_on_a_fabricated_quote_is_never_reported(self):
        llm = StubLlmProvider(
            {
                "claim_support": {
                    "quote": "this sentence appears nowhere in the abstract at all",
                    "grade": "not_supported",
                    "note": "Model was confident.",
                }
            }
        )
        findings = asyncio.run(
            self.build(llm).review(
                self.document_citing(), [resolved_reference()], find_missing_work=False
            )
        )

        assert findings == []

    def test_findings_anchor_to_real_spans_in_the_document(self):
        llm = StubLlmProvider(
            {
                "claim_support": {
                    "quote": "Experiments on two machine translation tasks show these "
                    "models to be superior in quality",
                    "grade": "partially_supports",
                    "note": "Narrower.",
                }
            }
        )
        document = self.document_citing()
        findings = asyncio.run(
            self.build(llm).review(document, [resolved_reference()], find_missing_work=False)
        )

        finding = findings[0]
        target = document.block(finding.block_id)
        assert target is not None
        assert target.display_text[finding.start : finding.end].strip() == finding.sentence

    def test_an_empty_review_is_a_valid_outcome(self):
        findings = asyncio.run(
            self.build(StubLlmProvider()).review(
                self.document_citing(), [resolved_reference()], find_missing_work=False
            )
        )

        assert findings == []


# Notes
#
# Every test here runs with no API key and no network, because the LLM sits
# behind a protocol and the stub returns canned JSON. The three passes, the
# quote verification and the finding assembly are all exercised offline.
#
# TestQuoteVerification and
# test_a_fabricated_quote_is_downgraded_whatever_the_model_claimed are the two
# that matter most. Together they assert the property the whole stage is built
# to guarantee: a model can claim "supports" as confidently as it likes, and if
# its quote is not literally present in the abstract the finding is downgraded
# to insufficient_evidence. The guarantee is enforced by string matching, so it
# holds for any model.
#
# test_a_finding_built_on_a_fabricated_quote_is_never_reported carries that
# through to the orchestrator: not only is the grade downgraded, the finding
# never reaches the user at all, because is_grounded requires at least one
# verified quote.
#
# test_findings_anchor_to_real_spans_in_the_document checks the other half of
# the design. It slices the document's own prose with the finding's offsets and
# requires the result to equal the reported sentence, which is only possible
# because sentences are derived in code rather than returned by the model.
#
# test_an_out_of_range_index_is_discarded guards the same idea in the claim
# pass: the model answers with indices into a list we supplied, and an index we
# did not offer is thrown away rather than trusted.
#
# test_an_empty_review_is_a_valid_outcome exists because a pipeline that only
# works when the model has something to say will fall over on the first clean
# paper.


class TestNonCitingBlocks:
    def document_with_abstract_and_body(self):
        return Document(
            id="d", paper_id="p", title="T",
            sections=[
                Section(id="s_front", title="Abstract", blocks=[
                    Block(id="s_front.p0", kind="abstract", inlines=[
                        TextRun(text="Dynamic Master Logic provides a hierarchical framework for systems."),
                    ]),
                ]),
                Section(id="s0", title="Introduction", blocks=[
                    Block(id="s0.p0", kind="paragraph", inlines=[
                        TextRun(text="Prior work established that recurrent models dominate this task."),
                    ]),
                ]),
            ],
        )

    def test_abstract_sentences_are_never_flagged_as_needing_a_citation(self):
        llm = StubLlmProvider({
            "uncited_claims": {
                "claims": [{"index": 0, "needs_citation": True, "reason": "factual"}]
            }
        })
        provider = ReviewProvider(
            sentences=SentenceProvider(),
            claims=ClaimProvider(llm),
            support=SupportProvider(llm),
            discovery=None,
        )

        findings = asyncio.run(
            provider.review(self.document_with_abstract_and_body(), [], check_support=False)
        )

        assert findings
        assert all(f.block_id != "s_front.p0" for f in findings)

    def test_body_paragraphs_are_still_flagged(self):
        llm = StubLlmProvider({
            "uncited_claims": {
                "claims": [{"index": 0, "needs_citation": True, "reason": "prior work"}]
            }
        })
        provider = ReviewProvider(
            sentences=SentenceProvider(),
            claims=ClaimProvider(llm),
            support=SupportProvider(llm),
            discovery=None,
        )

        findings = asyncio.run(
            provider.review(self.document_with_abstract_and_body(), [], check_support=False)
        )

        assert [f.block_id for f in findings] == ["s0.p0"]
