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
