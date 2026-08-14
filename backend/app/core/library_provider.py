from app.core.storage_provider import StorageProvider
from app.domain.library import Library, Reference


class LibraryProvider:
    def __init__(self, storage: StorageProvider) -> None:
        self._storage = storage

    def load(self, paper_id: str) -> Library:
        payload = self._storage.read_library(paper_id)
        if payload is None:
            return Library(paper_id=paper_id)
        return Library.model_validate_json(payload)

    def merge(self, paper_id: str, references: list[Reference]) -> Library:
        library = self.load(paper_id)
        known = library.ids

        for reference in references:
            if reference.id in known:
                continue
            library.references.append(reference)
            known.add(reference.id)

        self._storage.save_library(paper_id, library.model_dump_json(indent=2))
        return library
