from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.modules.editing.api.edit_routes import router as editing_router
from app.modules.export.api.export_routes import router as export_router
from app.modules.extraction.api.extraction_routes import router as extraction_router
from app.modules.papers.api.paper_routes import router as papers_router
from app.modules.resolution.api.resolution_routes import router as resolution_router
from app.modules.review.api.review_routes import router as review_router


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(title=settings.app_name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(papers_router, prefix=settings.api_prefix)
    app.include_router(extraction_router, prefix=settings.api_prefix)
    app.include_router(resolution_router, prefix=settings.api_prefix)
    app.include_router(review_router, prefix=settings.api_prefix)
    app.include_router(editing_router, prefix=settings.api_prefix)
    app.include_router(export_router, prefix=settings.api_prefix)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
