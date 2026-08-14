from pathlib import Path

from app.core.exceptions import PaperNotFoundError, StorageError

ORIGINAL_FILENAME = "original.pdf"
TEI_FILENAME = "grobid.tei.xml"
LIBRARY_FILENAME = "library.json"
REVISION_PREFIX = "rev_"
LIBRARY_FILENAME = "library.json"


class StorageProvider:
    def __init__(self, papers_dir: Path) -> None:
        self._papers_dir = papers_dir

    def paper_dir(self, paper_id: str) -> Path:
        return self._papers_dir / paper_id

    def original_path(self, paper_id: str) -> Path:
        return self.paper_dir(paper_id) / ORIGINAL_FILENAME

    def tei_path(self, paper_id: str) -> Path:
        return self.paper_dir(paper_id) / TEI_FILENAME

    def revision_path(self, paper_id: str, revision: int) -> Path:
        return self.paper_dir(paper_id) / f"{REVISION_PREFIX}{revision}.json"

    def library_path(self, paper_id: str) -> Path:
        return self.paper_dir(paper_id) / LIBRARY_FILENAME

    def exists(self, paper_id: str) -> bool:
        return self.original_path(paper_id).is_file()

    def save_original(self, paper_id: str, content: bytes) -> Path:
        return self._write_bytes(self.original_path(paper_id), content)

    def read_original(self, paper_id: str) -> bytes:
        path = self.original_path(paper_id)
        if not path.is_file():
            raise PaperNotFoundError(f"No paper stored under id '{paper_id}'.")
        try:
            return path.read_bytes()
        except OSError as exc:
            raise StorageError(f"Could not read paper '{paper_id}'.") from exc

    def save_tei(self, paper_id: str, tei_xml: str) -> Path:
        return self._write_text(self.tei_path(paper_id), tei_xml)

    def read_tei(self, paper_id: str) -> str | None:
        path = self.tei_path(paper_id)
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StorageError(f"Could not read TEI for paper '{paper_id}'.") from exc

    def save_revision(self, paper_id: str, revision: int, payload: str) -> Path:
        return self._write_text(self.revision_path(paper_id, revision), payload)

    def read_revision(self, paper_id: str, revision: int) -> str | None:
        path = self.revision_path(paper_id, revision)
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StorageError(
                f"Could not read revision {revision} of paper '{paper_id}'."
            ) from exc

    def save_library(self, paper_id: str, payload: str) -> Path:
        return self._write_text(self.library_path(paper_id), payload)

    def read_library(self, paper_id: str) -> str | None:
        path = self.library_path(paper_id)
        if not path.is_file():
            return None
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StorageError(
                f"Could not read the library for paper '{paper_id}'."
            ) from exc

    def revisions(self, paper_id: str) -> list[int]:
        directory = self.paper_dir(paper_id)
        if not directory.is_dir():
            return []

        found: list[int] = []
        for path in directory.glob(f"{REVISION_PREFIX}*.json"):
            try:
                found.append(int(path.stem[len(REVISION_PREFIX) :]))
            except ValueError:
                continue
        return sorted(found)

    def latest_revision(self, paper_id: str) -> int | None:
        found = self.revisions(paper_id)
        return found[-1] if found else None

    def _write_bytes(self, target: Path, content: bytes) -> Path:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        except OSError as exc:
            raise StorageError(f"Could not write '{target.name}' to disk.") from exc
        return target

    def _write_text(self, target: Path, content: str) -> Path:
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except OSError as exc:
            raise StorageError(f"Could not write '{target.name}' to disk.") from exc
        return target


# Notes
#
# One directory per paper, holding everything about that manuscript:
#
#     data/papers/<paper_id>/
#         original.pdf      written once at upload, only ever read afterwards
#         grobid.tei.xml    raw parser output, kept verbatim
#         library.json      every reference ever known, append-only
#         rev_0.json        the extraction result
#         rev_1.json        after the first approved edit
#
# original.pdf is never opened for writing after upload. That is a product
# guarantee rather than a convention: the user must be able to download their
# untouched file at any point, which is the answer to the fear that an AI
# quietly rewrote their manuscript.
#
# The raw TEI is kept for two reasons. A bad parse can be diagnosed by reading
# exactly what GROBID said rather than guessing, and any uploaded paper can be
# promoted to a committed test fixture, which is what lets the parser be tested
# without a container.
#
# library.json is append-only and separate from the revisions. A reference is
# a fact about the literature rather than a fact about one draft, so it does
# not belong inside a document revision that an edit may replace. Keeping it
# apart is what lets rev_3 cite a work that was discovered while producing
# rev_2, and what stops an undo from deleting a reference some other revision
# still points at.
#
# It also has to exist before stage 4 can check anything. The edit invariant
# asks "is this a real work the agent is allowed to cite?", and recomputing the
# answer would mean re-running resolution and spending API quota on every
# keystroke.
#
# revisions() reads the directory rather than trusting a counter, because the
# highest revision on disk is the truth and a stored number is one more thing
# that can disagree with it after a crash. Files that do not parse as rev_<n>
# are skipped rather than raising: an unrelated file appearing in the folder
# should not be able to break loading a paper.
#
# This lives in core rather than inside the papers module because the on-disk
# layout of a paper is shared infrastructure. Extraction writes TEI and
# revisions next to a PDF that upload wrote, and export will later read those
# revisions. Reaching across module boundaries for that would put one feature
# module in every other feature module's import graph.
