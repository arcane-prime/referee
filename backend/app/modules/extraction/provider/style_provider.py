import re

from app.domain.document import CitationStyle, CiteNode

NUMBERED_PATTERN = re.compile(r"^[\[\(]?\s*\d+(\s*[-–—,;]\s*\d+)*\s*[\]\)]?$")
AUTHOR_YEAR_PATTERN = re.compile(r"[A-Za-z]{2,}.*\b(1[6-9]\d{2}|20\d{2})\b")

MIN_SAMPLES = 3
CONFIDENCE_THRESHOLD = 0.7


class StyleProvider:
    def detect(self, cite_nodes: list[CiteNode]) -> tuple[CitationStyle, float]:
        markers = [
            node.raw_marker.strip()
            for node in cite_nodes
            if node.raw_marker and node.raw_marker.strip()
        ]

        if len(markers) < MIN_SAMPLES:
            return "unknown", 0.0

        numbered = 0
        author_year = 0

        for marker in markers:
            if NUMBERED_PATTERN.match(marker):
                numbered += 1
            elif AUTHOR_YEAR_PATTERN.search(marker):
                author_year += 1

        total = len(markers)
        numbered_share = numbered / total
        author_year_share = author_year / total

        if numbered_share >= CONFIDENCE_THRESHOLD:
            return "ieee", round(numbered_share, 3)
        if author_year_share >= CONFIDENCE_THRESHOLD:
            return "apa", round(author_year_share, 3)

        return "unknown", round(max(numbered_share, author_year_share), 3)


# Notes
#
# This is the only place in extraction that infers rather than records.
# Everything else writes down what the page said; this guesses a style from a
# sample of markers, so it returns a confidence alongside the answer and falls
# back to "unknown" rather than to a plausible-looking result.
#
# "unknown" is a real, useful outcome. The user picks the style in the UI, and
# a paper that renders correctly because the user chose is strictly better than
# one that renders wrongly because a heuristic was confident.
#
# The heuristic itself is deliberately dull. A marker of digits and separators,
# with or without brackets, is numbered. A marker containing letters and a
# plausible publication year is author-year. Below three markers there is not
# enough evidence to call it at all.
#
# ieee and apa here name the *family* of style, not the exact stylesheet. The
# actual formatting is done later by citeproc from a .csl file, so this only
# has to be right about which family to default the picker to.
