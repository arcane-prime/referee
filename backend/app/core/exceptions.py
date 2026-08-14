from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class RefereeError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidUploadError(RefereeError):
    status_code = 400
    code = "invalid_upload"


class UploadTooLargeError(RefereeError):
    status_code = 413
    code = "upload_too_large"


class PaperNotFoundError(RefereeError):
    status_code = 404
    code = "paper_not_found"


class StorageError(RefereeError):
    status_code = 500
    code = "storage_error"


class ParserUnavailableError(RefereeError):
    status_code = 502
    code = "parser_unavailable"


class ExtractionFailedError(RefereeError):
    status_code = 422
    code = "extraction_failed"


class SearchUnavailableError(RefereeError):
    status_code = 502
    code = "search_unavailable"


class NotExtractedError(RefereeError):
    status_code = 409
    code = "not_extracted"


class ReviewUnavailableError(RefereeError):
    status_code = 502
    code = "review_unavailable"


class EditConflictError(RefereeError):
    status_code = 409
    code = "edit_conflict"


class EditRefusedError(RefereeError):
    status_code = 422
    code = "edit_refused"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RefereeError)
    async def handle_referee_error(_: Request, exc: RefereeError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "detail": exc.detail},
        )
