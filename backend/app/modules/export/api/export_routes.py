from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse

from app.modules.editing.api.dependencies import get_revision_provider
from app.modules.editing.provider.revision_provider import RevisionProvider
from app.modules.export.api.dependencies import get_export_provider
from app.modules.export.dto.export_dto import ExportInfoDto
from app.modules.export.provider import bibliography_provider
from app.modules.export.provider.export_provider import ExportProvider

router = APIRouter(tags=["export"])


@router.get(
    "/papers/{paper_id}/export",
    response_model=ExportInfoDto,
    status_code=status.HTTP_200_OK,
    summary="What can be exported, and in which citation styles",
)
async def export_info(
    paper_id: str,
    revisions: RevisionProvider = Depends(get_revision_provider),
) -> ExportInfoDto:
    document, number = revisions.load(paper_id)

    return ExportInfoDto(
        paper_id=paper_id,
        revision=number,
        available_revisions=revisions.available(paper_id),
        detected_style=document.style,
        available_styles=bibliography_provider.available_styles(),
    )


@router.get(
    "/papers/{paper_id}/export.tex",
    response_class=PlainTextResponse,
    status_code=status.HTTP_200_OK,
    summary="Export the paper as LaTeX with a citeproc-rendered bibliography",
)
async def export_latex(
    paper_id: str,
    revision: int | None = Query(default=None),
    style: str | None = Query(default=None),
    export: ExportProvider = Depends(get_export_provider),
) -> PlainTextResponse:
    source, number, chosen, entries = export.latex(
        paper_id=paper_id, revision=revision, style=style
    )

    return PlainTextResponse(
        content=source,
        media_type="application/x-tex; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{paper_id}_rev{number}.tex"'
            ),
            "X-Referee-Style": chosen,
            "X-Referee-Revision": str(number),
            "X-Referee-Bibliography-Entries": str(entries),
        },
    )
