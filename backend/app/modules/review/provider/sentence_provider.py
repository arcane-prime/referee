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
