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


# Notes
#
# The PDF check reads the magic bytes rather than trusting the filename or the
# browser-supplied content type. Both of those are attacker-controlled and
# routinely wrong even when nobody is being hostile.
#
# The size limit is enforced here on the materialised bytes. FastAPI's
# UploadFile spools large uploads to a temp file, so a very large request is
# not held in memory before we reject it, but it is still transferred in full.
# A streaming guard at the ASGI layer is the stricter fix and is deliberately
# left out at this stage.
#
# This provider imports no web framework. It takes bytes, returns a DTO, and
# raises domain errors, which is what makes it testable without a running
# server.
