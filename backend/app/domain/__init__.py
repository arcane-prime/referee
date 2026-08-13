from app.domain.csl import CSLDate, CSLItem, CSLName, CSLType
from app.domain.document import (
    FLOATS_SECTION_ID,
    FRONT_MATTER_SECTION_ID,
    Block,
    BlockKind,
    CitationStyle,
    CiteNode,
    Document,
    Inline,
    MathNode,
    Section,
    TextRun,
    XRefNode,
)
from app.domain.geometry import BBox
from app.domain.library import Library, ParseQuality, RawReference

__all__ = [
    "BBox",
    "Block",
    "BlockKind",
    "CSLDate",
    "CSLItem",
    "CSLName",
    "CSLType",
    "CitationStyle",
    "CiteNode",
    "Document",
    "FLOATS_SECTION_ID",
    "FRONT_MATTER_SECTION_ID",
    "Inline",
    "Library",
    "MathNode",
    "ParseQuality",
    "RawReference",
    "Section",
    "TextRun",
    "XRefNode",
]


# Notes
#
# This package imports nothing but Pydantic. That constraint is deliberate:
# every stage's input and output type lives here with zero I/O, so the seams
# between extraction, resolution, review, edit and export are visible from type
# signatures alone.
#
# These are shared domain models rather than any one module's DTOs. Extraction
# creates them, review reads them, edit rewrites them and export renders them,
# so they sit outside modules/ and belong to none of them.
