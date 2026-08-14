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


# Notes
#
# Providers raise these domain errors and never import FastAPI. The single
# handler registered here is the only place that knows how a domain failure
# becomes an HTTP response, which keeps the logic layer framework-free and
# directly unit-testable.
#
# The response shape is {code, detail}. `code` is stable and meant to be
# switched on by the frontend; `detail` is human-readable and may change.
#
# ParserUnavailableError is a 502 rather than a 500 because the failure is in
# an upstream service we depend on, not in this application. The distinction
# matters to the caller: retrying is reasonable, and nothing was half-saved.
#
# ExtractionFailedError is a 422 and means the opposite: the parser answered,
# but its output could not be turned into a document. That is a property of the
# uploaded file, so retrying the same PDF will not help.
#
# SearchUnavailableError mirrors ParserUnavailableError for the literature
# databases: the failure is upstream, nothing was half-saved, and retrying is
# reasonable.
#
# NotExtractedError is a 409 rather than a 404. The paper exists, but the
# caller asked for something that requires a step they have not run yet, so the
# fix is to call extract first rather than to correct the id.
#
# EditConflictError is a 409 for the same reason: the request was well formed
# but the paper moved underneath it. A proposal computed against rev_2 cannot
# be applied on top of rev_3, because the blocks it describes are no longer the
# blocks on disk. Re-running the command is the fix, and refusing is the only
# safe answer since applying it would write a document neither revision
# describes.
#
# EditRefusedError is a 422 and means the edit itself was unacceptable rather
# than the request being malformed: a rewrite that would have dropped a
# citation, or an insertion naming a reference the agent is not allowed to
# cite. Nothing was written. The detail names what was lost or refused, because
# that sentence is shown to the researcher.
