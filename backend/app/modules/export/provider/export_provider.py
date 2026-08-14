from app.core.library_provider import LibraryProvider
from app.domain.document import Document
from app.modules.editing.provider.revision_provider import RevisionProvider
from app.modules.export.provider import bibliography_provider, latex_provider


class ExportProvider:
    def __init__(
        self,
        revisions: RevisionProvider,
        library: LibraryProvider,
    ) -> None:
        self._revisions = revisions
        self._library = library

    def latex(
        self,
        paper_id: str,
        revision: int | None = None,
        style: str | None = None,
    ) -> tuple[str, int, str, int]:
        document, number = self._revisions.load(paper_id, revision)
        library = self._library.load(paper_id)

        chosen = bibliography_provider.resolve_style(document.style, style)
        cited = _cited_ids(document)

        items = bibliography_provider.csl_items(library, cited_ids=cited)
        entries = bibliography_provider.render(items, chosen)

        source = latex_provider.render_document(document, entries, chosen)
        return source, number, chosen, len(entries)


def _cited_ids(document: Document) -> set[str]:
    return set(document.ref_id_counts())
