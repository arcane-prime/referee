from pathlib import Path

from citeproc import (
    Citation,
    CitationItem,
    CitationStylesBibliography,
    CitationStylesStyle,
    formatter,
)
from citeproc.source.json import CiteProcJSON

from app.domain.document import CitationStyle
from app.domain.library import Library, Reference

STYLES_DIR = Path(__file__).resolve().parent.parent / "styles"
FALLBACK_STYLE: CitationStyle = "ieee"
DEFAULT_CSL_TYPE = "article-journal"


def available_styles() -> list[str]:
    return sorted(path.stem for path in STYLES_DIR.glob("*.csl"))


def style_path(style: str) -> Path:
    candidate = STYLES_DIR / f"{style}.csl"
    if candidate.is_file():
        return candidate
    return STYLES_DIR / f"{FALLBACK_STYLE}.csl"


def resolve_style(document_style: CitationStyle, requested: str | None) -> str:
    if requested and (STYLES_DIR / f"{requested}.csl").is_file():
        return requested
    if document_style != "unknown" and (
        STYLES_DIR / f"{document_style}.csl"
    ).is_file():
        return document_style
    return FALLBACK_STYLE


def csl_items(library: Library, cited_ids: set[str] | None = None) -> list[dict]:
    items: list[dict] = []

    for reference in library.references:
        if cited_ids is not None and reference.id not in cited_ids:
            continue

        item = _csl_item(reference)
        if item is not None:
            items.append(item)

    return items


def render(items: list[dict], style: str) -> list[tuple[str, str]]:
    if not items:
        return []

    source = CiteProcJSON(items)
    stylesheet = CitationStylesStyle(str(style_path(style)), validate=False)
    bibliography = CitationStylesBibliography(stylesheet, source, formatter.plain)

    for item in items:
        bibliography.register(Citation([CitationItem(item["id"])]))

    rendered = [str(entry).strip() for entry in bibliography.bibliography()]
    keys = [item["id"] for item in items]

    return list(zip(keys, rendered, strict=True))


def _csl_item(reference: Reference) -> dict | None:
    csl = reference.csl
    if csl is None:
        return None

    item = csl.to_csl_json()
    item["id"] = reference.id
    item.setdefault("type", DEFAULT_CSL_TYPE)

    if not item.get("title"):
        item["title"] = reference.raw

    return item
