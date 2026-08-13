import re

from app.domain.document import Block, CiteNode, Document, TextRun
from app.domain.review import Sentence

ABBREVIATIONS = {
    "al", "eg", "ie", "cf", "etc", "vs", "fig", "figs", "eq", "eqs", "ref",
    "refs", "sec", "secs", "no", "nos", "vol", "pp", "ca", "approx", "dr",
    "prof", "mr", "mrs", "ms", "st", "inc", "ltd", "jr", "sr", "ed", "eds",
}

SENTENCE_END = re.compile(r"[.!?]['\")\]]*\s+")
TRAILING_TOKEN = re.compile(r"([A-Za-z]+)\.$")
INITIAL = re.compile(r"\b[A-Z]\.$")

MIN_SENTENCE_CHARS = 12
MIN_REPORTABLE_CHARS = 25


class SentenceProvider:
    def for_block(self, block: Block) -> list[Sentence]:
        text, node_offsets = self._flatten(block)
        if not text.strip():
            return []

        sentences: list[Sentence] = []
        for index, (start, end) in enumerate(self._spans(text)):
            body = text[start:end].strip()
            if not body:
                continue

            sentences.append(
                Sentence(
                    block_id=block.id,
                    index=index,
                    text=body,
                    start=start,
                    end=end,
                    cite_nodes=[
                        node
                        for offset, node in node_offsets
                        if start <= offset <= end
                    ],
                )
            )
        return sentences

    def for_document(self, document: Document) -> list[Sentence]:
        return [
            sentence
            for block in document.blocks()
            if block.kind in ("paragraph", "abstract")
            for sentence in self.for_block(block)
            if self._is_reportable(sentence)
        ]

    def _is_reportable(self, sentence: Sentence) -> bool:
        if sentence.is_cited:
            return True
        return len(sentence.text) >= MIN_REPORTABLE_CHARS

    def _flatten(self, block: Block) -> tuple[str, list[tuple[int, CiteNode]]]:
        pieces: list[str] = []
        offsets: list[tuple[int, CiteNode]] = []
        cursor = 0

        for node in block.inlines:
            if isinstance(node, TextRun):
                pieces.append(node.text)
                cursor += len(node.text)
            elif isinstance(node, CiteNode):
                offsets.append((cursor, node))

        return "".join(pieces), offsets

    def _spans(self, text: str) -> list[tuple[int, int]]:
        spans: list[tuple[int, int]] = []
        start = 0

        for match in SENTENCE_END.finditer(text):
            end = match.end()
            candidate = text[start:end]

            if self._is_false_break(candidate):
                continue
            if len(candidate.strip()) < MIN_SENTENCE_CHARS:
                continue

            spans.append((start, end))
            start = end

        if start < len(text) and text[start:].strip():
            spans.append((start, len(text)))

        return spans or [(0, len(text))]

    def _is_false_break(self, candidate: str) -> bool:
        stripped = candidate.strip()
        if not stripped.endswith("."):
            return False

        if INITIAL.search(stripped):
            return True

        match = TRAILING_TOKEN.search(stripped)
        if match and match.group(1).lower() in ABBREVIATIONS:
            return True

        return False


# Notes
#
# Sentences are computed here and never stored, so there is nothing to keep in
# sync with the document. Splitting is done over the block's prose, and each
# CiteNode is placed at the character offset where it sits between text runs.
# A node therefore lands in the sentence whose span contains it, which is how a
# claim gets connected to the references supporting it.
#
# This is why review can anchor its findings. Every sentence knows its block
# id, its index and its exact offsets, all derived from our own model, so a
# finding always points at real text the UI can highlight. Asking a model to
# return the claim it judged would give paraphrased text that matches nothing
# in the document.
#
# Offsets are measured over the text runs only, with citations contributing no
# characters, which is consistent with Block.display_text. The stored data has
# no markers in it, so the spans describe exactly what a reader of the prose
# would see.
#
# Splitting on punctuation is a heuristic, and the failure mode that matters is
# breaking mid-sentence at an abbreviation. Academic prose is full of them, and
# "Vaswani et al. showed" split at "al." would produce a fragment and orphan
# the citation attached to the real sentence. Initials and a list of common
# abbreviations are therefore treated as false breaks, and very short fragments
# are folded into the following sentence rather than reported as claims.
#
# Only paragraphs and the abstract are walked. Captions cite work and are kept
# in the document for the citation count, but a caption is a label rather than
# a claim, and reviewing one as if it were an argument produces noise.
#
# for_document additionally drops very short uncited fragments. Real GROBID
# output contains blocks holding a single word, because a display formula
# splits "the value" and "where" away from the sentence around it. Those are
# not sentences, and counting them would overstate how much of the paper was
# examined in a summary meant to be read honestly.
#
# The filter deliberately never drops a sentence carrying a citation, however
# short. A short cited fragment is still a citation that must be checked, and
# silently skipping one would make the review quietly incomplete.
