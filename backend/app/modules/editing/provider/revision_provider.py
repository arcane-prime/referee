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


# Notes
#
# Revisions are append-only. save() writes rev_N+1 and never touches rev_N, so
# undo is pointing at a smaller number rather than a reverse operation that has
# to be correct. The original PDF is never rewritten at all, which is the
# product promise behind the whole stage: whatever the agent does, the file the
# researcher uploaded is still there.
#
# The latest revision is read off the directory rather than tracked in a
# counter. The files are the truth, and a counter is one more thing that can
# disagree with them after a crash.
#
# Reading the library is delegated to core rather than reimplemented, because
# resolution writes that file and editing only reads it. Two copies of the
# merge rule is how an append-only guarantee stops being one.
