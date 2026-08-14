from app.core.exceptions import NotExtractedError
from app.core.library_provider import LibraryProvider
from app.core.storage_provider import StorageProvider
from app.domain.document import Document
from app.domain.library import Library


class RevisionProvider:
    def __init__(self, storage: StorageProvider, library: LibraryProvider) -> None:
        self._storage = storage
        self._library = library

    def latest_number(self, paper_id: str) -> int:
        latest = self._storage.latest_revision(paper_id)
        if latest is None:
            raise NotExtractedError(
                f"Paper '{paper_id}' has not been extracted yet. Run extract first."
            )
        return latest

    def load(self, paper_id: str, revision: int | None = None) -> tuple[Document, int]:
        number = self.latest_number(paper_id) if revision is None else revision

        payload = self._storage.read_revision(paper_id, number)
        if payload is None:
            raise NotExtractedError(
                f"Paper '{paper_id}' has no revision {number}."
            )

        return Document.model_validate_json(payload), number

    def save(self, paper_id: str, document: Document, revision: int) -> None:
        document.revision = revision
        self._storage.save_revision(
            paper_id, revision, document.model_dump_json(indent=2)
        )

    def available(self, paper_id: str) -> list[int]:
        return self._storage.revisions(paper_id)

    def load_library(self, paper_id: str) -> Library:
        return self._library.load(paper_id)
