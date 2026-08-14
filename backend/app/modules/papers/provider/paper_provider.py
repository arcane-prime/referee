from datetime import datetime, timezone
from uuid import uuid4

from app.core.exceptions import InvalidUploadError, UploadTooLargeError
from app.core.storage_provider import StorageProvider
from app.modules.papers.dto.paper_dto import UploadedPaperDto

PDF_MAGIC = b"%PDF-"
PAPER_ID_PREFIX = "paper_"


class PaperProvider:
    def __init__(self, storage: StorageProvider, max_upload_bytes: int) -> None:
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes

    def create_from_upload(self, filename: str, content: bytes) -> UploadedPaperDto:
        self._validate(filename, content)

        paper_id = self._new_paper_id()
        self._storage.save_original(paper_id, content)

        return UploadedPaperDto(
            paper_id=paper_id,
            filename=filename,
            size_bytes=len(content),
            uploaded_at=datetime.now(timezone.utc),
        )

    def _validate(self, filename: str, content: bytes) -> None:
        if not content:
            raise InvalidUploadError("The uploaded file is empty.")

        if len(content) > self._max_upload_bytes:
            limit_mb = self._max_upload_bytes / (1024 * 1024)
            raise UploadTooLargeError(f"The file exceeds the {limit_mb:.0f} MB limit.")

        if not content.startswith(PDF_MAGIC):
            raise InvalidUploadError(f"'{filename}' is not a PDF.")

    @staticmethod
    def _new_paper_id() -> str:
        return f"{PAPER_ID_PREFIX}{uuid4().hex[:12]}"
