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
