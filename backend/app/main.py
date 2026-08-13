from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.modules.extraction.api.extraction_routes import router as extraction_router
from app.modules.papers.api.paper_routes import router as papers_router


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

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


# Notes
#
# create_app is a factory rather than a module-level assembly so tests can
# build an isolated instance with their own settings.
#
# Modules register themselves by exporting a router. Adding the parsing or
# review module later means one import and one include_router call here, and
# nothing else in this file changes.
