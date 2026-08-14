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


# Notes
#
# The library is written by resolution and read by editing, so it lives in core
# beside the storage layout rather than inside either module. Putting it in
# resolution would place that module in editing's import graph for the sake of
# one file on disk; putting it in editing would mean extraction importing the
# module that imports it.
#
# merge() is append-only by id and never overwrites an existing entry. Two
# consequences, both deliberate. A reference discovered while producing one
# revision is still citable from the next, so approving an edit cannot orphan
# it. And re-running extraction on a paper cannot downgrade a reference that
# was resolved earlier, which matters because resolution quality depends on
# whether the databases were reachable that day.
#
# A missing library.json loads as an empty Library rather than raising. A paper
# extracted while OpenAlex was out of quota simply has nothing the agent is
# allowed to cite yet, and that falls out of check_citable finding no entry
# rather than needing a special case anywhere.
