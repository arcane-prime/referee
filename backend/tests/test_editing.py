import asyncio

import pytest

from app.core.exceptions import EditConflictError, EditRefusedError
from app.core.library_provider import LibraryProvider
from app.core.storage_provider import StorageProvider
from app.domain.csl import CSLItem
from app.domain.document import (
    Block,
    CiteNode,
    Document,
    MathNode,
    Section,
    TextRun,
    XRefNode,
)
from app.domain.library import ExternalIds, Library, Reference, Resolution
from app.modules.editing.provider import operation_provider
from app.modules.editing.provider.edit_provider import EditProvider
from app.modules.editing.provider.invariant_provider import (
    InvariantViolation,
    check_citable,
    compare,
    enforce,
    ref_counts,
)
from app.modules.editing.provider.placeholder_provider import (
    PlaceholderMismatch,
    deflate,
    inflate,
    reordered,
    token_for,
    verify,
)
from app.modules.editing.provider.plan_provider import PlanProvider
from app.modules.editing.provider.revision_provider import RevisionProvider
from app.modules.editing.provider.writer_provider import WriterProvider
from app.modules.review.provider.stub_llm_provider import StubLlmProvider


def paragraph() -> Block:
    return Block(
        id="b_1",
        kind="paragraph",
        inlines=[
            TextRun(text="Transformers dominate NLP "),
            CiteNode(id="c_4", ref_ids=["ref_12"], raw_marker="[12]"),
            TextRun(text=". Recent work extends this to vision "),
            CiteNode(id="c_5", ref_ids=["ref_13", "ref_14"], raw_marker="[13, 14]"),
            TextRun(text=", with results in "),
            XRefNode(id="x_2", target_kind="table", label="Table 2"),
            TextRun(text="."),
        ],
    )


def test_deflate_hides_every_non_text_node_behind_a_token():
    deflated = deflate(paragraph().inlines)

    assert deflated.text == (
        "Transformers dominate NLP [[c_4]]. Recent work extends this to vision "
        "[[c_5]], with results in [[x_2]]."
    )
    assert deflated.tokens == {"c_4", "c_5", "x_2"}


def test_the_model_never_sees_a_ref_id():
    deflated = deflate(paragraph().inlines)

    assert "ref_12" not in deflated.text
    assert "ref_13" not in deflated.text
    assert "[12]" not in deflated.text


def test_round_trip_with_no_change_rebuilds_the_block_exactly():
    original = paragraph().inlines
    deflated = deflate(original)

    assert inflate(deflated.text, deflated.nodes) == original


def test_inflate_reuses_the_original_node_objects():
    original = paragraph().inlines
    deflated = deflate(original)

    rebuilt = inflate(deflated.text, deflated.nodes)
    cite = next(node for node in rebuilt if isinstance(node, CiteNode) and node.id == "c_5")

    assert cite.ref_ids == ["ref_13", "ref_14"]
    assert cite is deflated.nodes["c_5"]


def test_a_citation_may_move_and_keeps_its_ref_ids():
    deflated = deflate(paragraph().inlines)
    shortened = "Transformers dominate NLP and now vision [[c_5]] [[c_4]] (see [[x_2]])."

    rebuilt = inflate(shortened, deflated.nodes)
    cites = [node for node in rebuilt if isinstance(node, CiteNode)]

    assert [node.id for node in cites] == ["c_5", "c_4"]
    assert cites[0].ref_ids == ["ref_13", "ref_14"]
    assert cites[1].ref_ids == ["ref_12"]


def test_a_dropped_citation_is_refused_not_repaired():
    deflated = deflate(paragraph().inlines)
    lost = "Transformers dominate NLP and vision [[c_5]], shown in [[x_2]]."

    with pytest.raises(PlaceholderMismatch) as error:
        inflate(lost, deflated.nodes)

    assert "c_4" in error.value.reason
    assert "refused" in error.value.reason


def test_an_invented_marker_is_refused():
    deflated = deflate(paragraph().inlines)
    invented = (
        "Transformers dominate NLP [[c_4]] and vision [[c_5]] and audio [[c_9]], "
        "shown in [[x_2]]."
    )

    with pytest.raises(PlaceholderMismatch) as error:
        inflate(invented, deflated.nodes)

    assert "c_9" in error.value.reason
    assert "invented" in error.value.reason


def test_a_duplicated_marker_is_refused():
    deflated = deflate(paragraph().inlines)
    doubled = (
        "Transformers dominate NLP [[c_4]] and vision [[c_5]] [[c_4]], "
        "shown in [[x_2]]."
    )

    with pytest.raises(PlaceholderMismatch) as error:
        inflate(doubled, deflated.nodes)

    assert "c_4" in error.value.reason
    assert "twice" in error.value.reason


def test_an_empty_rewrite_loses_everything_and_is_refused():
    deflated = deflate(paragraph().inlines)

    with pytest.raises(PlaceholderMismatch):
        inflate("", deflated.nodes)


def test_a_block_with_no_citations_round_trips():
    inlines = [TextRun(text="A paragraph with nothing to protect.")]
    deflated = deflate(inlines)

    assert deflated.tokens == set()
    assert inflate("A shorter paragraph.", deflated.nodes) == [
        TextRun(text="A shorter paragraph.")
    ]


def test_formulas_and_cross_references_are_protected_too():
    inlines = [
        TextRun(text="We minimise "),
        MathNode(id="m_1", source="\\mathcal{L}(\\theta)"),
        TextRun(text=" as defined in "),
        XRefNode(id="x_7", target_kind="equation", label="Eq. 3"),
        TextRun(text="."),
    ]
    deflated = deflate(inlines)

    with pytest.raises(PlaceholderMismatch):
        inflate("We minimise the loss.", deflated.nodes)

    rebuilt = inflate("We minimise [[m_1]], see [[x_7]].", deflated.nodes)
    math = next(node for node in rebuilt if isinstance(node, MathNode))
    assert math.source == "\\mathcal{L}(\\theta)"


def test_duplicate_node_ids_in_one_block_are_rejected_at_deflate():
    inlines = [
        TextRun(text="First "),
        CiteNode(id="c_1", ref_ids=["ref_1"]),
        TextRun(text=" and again "),
        CiteNode(id="c_1", ref_ids=["ref_2"]),
    ]

    with pytest.raises(PlaceholderMismatch) as error:
        deflate(inlines)

    assert "c_1" in error.value.reason


def test_adjacent_tokens_do_not_produce_empty_text_runs():
    inlines = [
        CiteNode(id="c_1", ref_ids=["ref_1"]),
        CiteNode(id="c_2", ref_ids=["ref_2"]),
    ]
    deflated = deflate(inlines)
    rebuilt = inflate(deflated.text, deflated.nodes)

    assert all(not isinstance(node, TextRun) for node in rebuilt)
    assert len(rebuilt) == 2


def test_reordered_reports_nothing_when_order_is_unchanged():
    deflated = deflate(paragraph().inlines)
    same_order = "NLP [[c_4]], vision [[c_5]], table [[x_2]]."

    assert reordered(deflated, same_order) == []


def test_reordered_reports_the_markers_that_changed_places():
    deflated = deflate(paragraph().inlines)
    swapped = "Vision [[c_5]] then NLP [[c_4]], table [[x_2]]."

    assert reordered(deflated, swapped) == ["c_4", "c_5", "x_2"]


def test_verify_accepts_text_that_carries_every_token():
    verify("a [[c_1]] b [[c_2]]", {"c_1", "c_2"})


def test_token_for_matches_what_the_pattern_finds():
    deflated = deflate([CiteNode(id="c_42", ref_ids=["ref_1"])])

    assert deflated.text == token_for("c_42")


def fetched(ref_id: str) -> Reference:
    return Reference(
        id=ref_id,
        raw="Vaswani et al. Attention is all you need. 2017.",
        provenance="fetched_from_api",
        resolution=Resolution(
            status="resolved",
            matched=CSLItem(id=ref_id, title="Attention is all you need"),
            external_ids=ExternalIds(doi="10.5555/3295222"),
        ),
    )


def from_pdf(ref_id: str) -> Reference:
    return Reference(id=ref_id, raw="Some reference off the page.")


def test_ref_counts_counts_multiplicity_not_membership():
    inlines = [
        CiteNode(id="c_1", ref_ids=["ref_1"]),
        TextRun(text=" and "),
        CiteNode(id="c_2", ref_ids=["ref_1", "ref_2"]),
    ]

    assert ref_counts(inlines) == {"ref_1": 2, "ref_2": 1}


def test_compare_reports_a_citation_lost():
    delta = compare({"ref_1": 2, "ref_2": 1}, {"ref_1": 1, "ref_2": 1})

    assert delta.removed == ["ref_1"]
    assert delta.added == []


def test_shorten_must_leave_citation_counts_identical():
    with pytest.raises(InvariantViolation) as error:
        enforce("shorten_block", {"ref_1": 1, "ref_2": 1}, {"ref_1": 1})

    assert "ref_2" in error.value.reason
    assert "drop" in error.value.reason


def test_shorten_that_preserves_counts_passes():
    delta = enforce("shorten_block", {"ref_1": 1, "ref_2": 1}, {"ref_2": 1, "ref_1": 1})

    assert delta.is_empty


def test_a_rewrite_may_not_quietly_add_a_citation_either():
    with pytest.raises(InvariantViolation):
        enforce("rewrite_block", {"ref_1": 1}, {"ref_1": 1, "ref_9": 1})


def test_add_citation_may_increase_but_never_decrease():
    delta = enforce("add_citation", {"ref_1": 1}, {"ref_1": 1, "ref_9": 1})
    assert delta.added == ["ref_9"]

    with pytest.raises(InvariantViolation) as error:
        enforce("add_citation", {"ref_1": 1, "ref_2": 1}, {"ref_2": 1, "ref_9": 1})

    assert "ref_1" in error.value.reason


def test_delete_block_may_remove_but_the_loss_is_returned():
    delta = enforce("delete_block", {"ref_1": 1, "ref_2": 1}, {"ref_2": 1})

    assert delta.removed == ["ref_1"]


def test_an_operation_with_no_declared_rule_is_refused():
    with pytest.raises(InvariantViolation) as error:
        enforce("reticulate_splines", {}, {})

    assert "no citation rule" in error.value.reason


def test_the_agent_may_cite_a_reference_fetched_from_a_database():
    library = Library(paper_id="p_1", references=[fetched("ref_9")])

    check_citable(library, "ref_9")


def test_the_agent_may_not_cite_a_reference_only_parsed_from_the_pdf():
    library = Library(paper_id="p_1", references=[from_pdf("ref_3")])

    with pytest.raises(InvariantViolation) as error:
        check_citable(library, "ref_3")

    assert "fetched from a database" in error.value.reason


def test_the_agent_may_not_cite_a_reference_it_invented():
    library = Library(paper_id="p_1", references=[fetched("ref_9")])

    with pytest.raises(InvariantViolation) as error:
        check_citable(library, "ref_hallucinated")

    assert "not in this paper's library" in error.value.reason


def test_a_fetched_reference_with_no_external_id_is_still_refused():
    weak = Reference(id="ref_5", raw="Something", provenance="fetched_from_api")
    library = Library(paper_id="p_1", references=[weak])

    with pytest.raises(InvariantViolation):
        check_citable(library, "ref_5")


def test_apply_text_produces_a_patch_that_passed_both_guards():
    block = paragraph()
    shortened = "NLP and vision [[c_4]] [[c_5]], see [[x_2]]."

    patch = operation_provider.apply_text(block, shortened, "shorten_block")

    assert patch.block_id == "b_1"
    assert patch.citations.added == []
    assert patch.citations.removed == []
    assert patch.citations.moved == []


def test_a_patch_reports_citations_that_changed_places():
    block = paragraph()
    swapped = "Vision [[c_5]] then NLP [[c_4]], see [[x_2]]."

    patch = operation_provider.apply_text(block, swapped, "shorten_block")

    assert patch.citations.moved == ["c_4", "c_5", "x_2"]
    assert patch.citations.added == []
    assert patch.citations.removed == []


def test_add_citation_lands_before_the_final_full_stop():
    block = Block(
        id="b_2",
        kind="paragraph",
        inlines=[TextRun(text="Attention mechanisms scale well.")],
    )

    patch = operation_provider.add_citation(block, "ref_9", "c_e1")

    assert patch.citations.added == ["ref_9"]
    assert patch.after_text == "Attention mechanisms scale well [[c_e1]]."


def test_delete_block_reports_every_citation_it_takes_with_it():
    patch = operation_provider.delete_block(paragraph())

    assert patch.deleted is True
    assert sorted(patch.citations.removed) == ["ref_12", "ref_13", "ref_14"]


def document_with(block: Block) -> Document:
    return Document(
        id="d_1",
        paper_id="p_1",
        title="A paper",
        sections=[Section(id="s_1", title="Introduction", blocks=[block])],
    )


def build(tmp_path, answers: dict) -> tuple[EditProvider, StorageProvider]:
    storage = StorageProvider(papers_dir=tmp_path)
    llm = StubLlmProvider(answers=answers)

    provider = EditProvider(
        revisions=RevisionProvider(
            storage=storage, library=LibraryProvider(storage=storage)
        ),
        planner=PlanProvider(llm=llm),
        writer=WriterProvider(llm=llm),
    )
    return provider, storage


def seed(storage: StorageProvider, document: Document) -> None:
    storage.save_revision("p_1", 0, document.model_dump_json())


def test_a_shorten_command_produces_a_proposal_without_writing_anything(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "shorten the introduction",
                "operations": [
                    {"kind": "shorten_block", "block_id": "b_1", "target_ratio": 0.6}
                ],
                "note": None,
            },
            "edited_paragraph": {
                "text": "NLP and vision [[c_4]] [[c_5]], see [[x_2]]."
            },
        },
    )
    seed(storage, document_with(paragraph()))

    proposal = asyncio.run(provider.propose("p_1", "make the intro shorter"))

    assert len(proposal.patches) == 1
    assert proposal.base_revision == 0
    assert proposal.citations.removed == []
    assert storage.read_revision("p_1", 1) is None


def test_a_rewrite_that_drops_a_citation_is_reported_not_applied(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "shorten",
                "operations": [{"kind": "shorten_block", "block_id": "b_1"}],
                "note": None,
            },
            "edited_paragraph": {"text": "NLP and vision, see [[x_2]]."},
        },
    )
    seed(storage, document_with(paragraph()))

    proposal = asyncio.run(provider.propose("p_1", "make the intro shorter"))

    assert proposal.patches == []
    assert len(proposal.rejected) == 1
    assert "c_4" in proposal.rejected[0].reason
    assert "c_5" in proposal.rejected[0].reason


def test_approving_a_proposal_writes_the_next_revision(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "shorten",
                "operations": [{"kind": "shorten_block", "block_id": "b_1"}],
                "note": None,
            },
            "edited_paragraph": {
                "text": "NLP and vision [[c_4]] [[c_5]], see [[x_2]]."
            },
        },
    )
    seed(storage, document_with(paragraph()))

    proposal = asyncio.run(provider.propose("p_1", "shorten"))
    applied = provider.apply("p_1", proposal)

    assert applied.revision == 1
    assert applied.applied_blocks == ["b_1"]

    before = Document.model_validate_json(storage.read_revision("p_1", 0))
    after = Document.model_validate_json(storage.read_revision("p_1", 1))

    assert before.ref_id_counts() == after.ref_id_counts()
    assert storage.read_revision("p_1", 0) is not None


def test_a_tampered_proposal_that_drops_a_citation_is_refused_on_apply(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "shorten",
                "operations": [{"kind": "shorten_block", "block_id": "b_1"}],
                "note": None,
            },
            "edited_paragraph": {
                "text": "NLP and vision [[c_4]] [[c_5]], see [[x_2]]."
            },
        },
    )
    seed(storage, document_with(paragraph()))

    proposal = asyncio.run(provider.propose("p_1", "shorten"))
    proposal.patches[0].after = [
        node for node in proposal.patches[0].after if getattr(node, "id", "") != "c_4"
    ]

    with pytest.raises(EditRefusedError):
        provider.apply("p_1", proposal)

    assert storage.read_revision("p_1", 1) is None


def test_a_stale_proposal_is_refused(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "shorten",
                "operations": [{"kind": "shorten_block", "block_id": "b_1"}],
                "note": None,
            },
            "edited_paragraph": {
                "text": "NLP and vision [[c_4]] [[c_5]], see [[x_2]]."
            },
        },
    )
    seed(storage, document_with(paragraph()))

    proposal = asyncio.run(provider.propose("p_1", "shorten"))
    provider.apply("p_1", proposal)

    with pytest.raises(EditConflictError):
        provider.apply("p_1", proposal)


def test_the_agent_cannot_cite_a_reference_that_is_not_in_the_library(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "add a citation",
                "operations": [
                    {
                        "kind": "add_citation",
                        "block_id": "b_1",
                        "ref_id": "ref_invented",
                    }
                ],
                "note": None,
            }
        },
    )
    seed(storage, document_with(paragraph()))

    proposal = asyncio.run(provider.propose("p_1", "add more citations"))

    assert proposal.patches == []
    assert "not in this paper's library" in proposal.rejected[0].reason


def test_the_agent_may_cite_a_fetched_reference_from_the_library(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "add a citation",
                "operations": [
                    {"kind": "add_citation", "block_id": "b_1", "ref_id": "ref_9"}
                ],
                "note": None,
            }
        },
    )
    seed(storage, document_with(paragraph()))
    LibraryProvider(storage=storage).merge("p_1", [fetched("ref_9")])

    proposal = asyncio.run(provider.propose("p_1", "add more citations"))

    assert len(proposal.patches) == 1
    assert proposal.citations.added == ["ref_9"]
    assert proposal.citations.removed == []


def test_a_plan_naming_a_block_that_does_not_exist_is_dropped(tmp_path):
    provider, storage = build(
        tmp_path,
        {
            "edit_plan": {
                "intent": "shorten",
                "operations": [{"kind": "shorten_block", "block_id": "b_999"}],
                "note": None,
            }
        },
    )
    seed(storage, document_with(paragraph()))

    proposal = asyncio.run(provider.propose("p_1", "shorten"))

    assert proposal.patches == []
    assert proposal.rejected == []


def test_the_library_is_append_only(tmp_path):
    storage = StorageProvider(papers_dir=tmp_path)
    library = LibraryProvider(storage=storage)

    library.merge("p_1", [fetched("ref_1")])
    library.merge("p_1", [fetched("ref_2")])

    assert library.load("p_1").ids == {"ref_1", "ref_2"}


# Notes
#
# These tests are the reason the placeholder layer was built before anything
# that calls a model. Every one of them runs offline in milliseconds, because
# the citation-safety core is pure functions over the domain model.
#
# test_the_model_never_sees_a_ref_id is the load-bearing one. It asserts the
# negative that the whole design rests on: no reference id and no printed
# marker reaches the text handed to the LLM, so there is nothing for it to
# rewrite, retarget or invent.
#
# The three refusal tests fix the behaviour the brief calls non-negotiable. A
# rewrite that drops, invents or duplicates a marker raises rather than
# applying, and the reason names the marker so the failure can be shown to the
# user instead of logged. Repairing any of these would mean guessing what the
# author meant.
#
# test_a_citation_may_move_and_keeps_its_ref_ids is the counterweight to those.
# Citations are not frozen. A shortened paragraph is allowed to carry its
# citations to new positions, which is what the brief asks for when text moves
# or shrinks; what is forbidden is authoring them.
#
# test_inflate_reuses_the_original_node_objects checks identity rather than
# equality on purpose. Rebuilding an equal-looking CiteNode would pass an
# equality assertion while quietly proving the opposite of the design.
#
# The formula and cross-reference test exists because those nodes get the same
# protection for free. The brief only asks for citations, but a shorten that
# silently deleted an equation would be the same class of bug.
