"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models  # noqa: F401 — registers models with Base
from app.config import BASE_DIR, settings
from app.database import get_db, init_db
from app.routers.admin import router as admin_router
from app.routers.book import router as book_router
from app.routers.comment import router as comment_router
from app.routers.upload import router as upload_router
from app.services.embedding import EmbeddingUnavailableError
from app.services.llm import LLMError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    if not settings.ADMIN_PASSWORD:
        logger.warning(
            "ADMIN_PASSWORD is not set: /admin only works for direct localhost access, "
            "and is refused behind a reverse proxy"
        )
    if not settings.llm_configured:
        logger.warning("LLM_API_KEY is not set: comments will be queued for review")
    if not settings.ALLOW_UPLOADS:
        logger.info("Uploads are disabled (ALLOW_UPLOADS=false)")
    yield


app = FastAPI(title="SpoilerShield", lifespan=lifespan)


@app.middleware("http")
async def reject_cross_origin_writes(request: Request, call_next):
    """Cheap CSRF defence: browsers send Origin on cross-site POSTs.

    Same-origin form posts and curl/CLI clients (no Origin header) still work.
    """
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin:
            origin_host = urlparse(origin).netloc
            if origin == "null" or (origin_host and origin_host != request.headers.get("host", "")):
                return JSONResponse(
                    status_code=403, content={"detail": "跨站请求被拒绝"}
                )
    return await call_next(request)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "app" / "static")),
    name="static",
)

app.include_router(upload_router)
app.include_router(book_router)
app.include_router(comment_router)
app.include_router(admin_router)


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(EmbeddingUnavailableError)
async def embedding_error_handler(
    request: Request, exc: EmbeddingUnavailableError
) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/ping")
def ping():
    return {"status": "ok"}


@app.get("/healthz")
def healthz(db: Session = Depends(get_db)):
    """Readiness probe: checks the database and reports the configured model."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        logger.exception("Health check failed: database unavailable")
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "database unavailable"},
        )
    return {
        "status": "ok",
        "llm_model": settings.LLM_MODEL,
        "llm_configured": settings.llm_configured,
    }
