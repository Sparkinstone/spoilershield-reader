"""Book upload: validate, store safely, parse, embed in one transaction."""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Book, Paragraph
from app.services.embedding import EmbeddingService, EmbeddingUnavailableError
from app.services.parser import parse_file
from app.services.providers import get_embedding_service

router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"pdf", "epub", "txt"}
_CHUNK_SIZE = 1024 * 1024


@router.post("/upload")
def upload_book(
    file: UploadFile = File(...),
    title: str = Form(""),
    db: Session = Depends(get_db),
    embedding: EmbeddingService = Depends(get_embedding_service),
):
    if not settings.ALLOW_UPLOADS:
        raise HTTPException(status_code=403, detail="当前部署已关闭上传功能")

    original_name = os.path.basename(file.filename or "")
    extension = Path(original_name).suffix.lower().lstrip(".")
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型：{extension or '未知'}（仅支持 PDF / EPUB / TXT）",
        )

    book_title = (title or "").strip() or Path(original_name).stem or "未命名书籍"
    book_title = book_title[:200]

    upload_dir = settings.upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    # Never reuse the client-supplied name: it may contain path separators.
    stored_name = f"{uuid.uuid4().hex}.{extension}"
    file_path = upload_dir / stored_name
    max_bytes = int(settings.MAX_UPLOAD_MB * 1024 * 1024)

    book: Book | None = None
    try:
        size = 0
        with open(file_path, "wb") as handle:
            # This endpoint is intentionally sync: FastAPI runs it in the
            # threadpool, so parsing + embedding do not block the event loop.
            while chunk := file.file.read(_CHUNK_SIZE):
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过 {settings.MAX_UPLOAD_MB:g} MB 限制",
                    )
                handle.write(chunk)
        if size == 0:
            raise HTTPException(status_code=400, detail="文件为空")

        try:
            paragraphs = parse_file(str(file_path), extension)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if len(paragraphs) > settings.MAX_PARAGRAPHS:
            raise HTTPException(
                status_code=413,
                detail=f"段落数 {len(paragraphs)} 超过 {settings.MAX_PARAGRAPHS} 上限，请拆分后上传",
            )

        vectors = embedding.encode_batch([paragraph["content"] for paragraph in paragraphs])
        if len(vectors) != len(paragraphs):
            raise HTTPException(status_code=500, detail="向量生成失败，请重试")

        book = Book(
            title=book_title,
            filename=stored_name,
            file_type=extension,
            total_paragraphs=len(paragraphs),
        )
        db.add(book)
        db.flush()

        db.add_all(
            [
                Paragraph(
                    book_id=book.id,
                    para_index=paragraph["para_index"],
                    page_num=paragraph.get("page_num"),
                    content=paragraph["content"],
                    embedding_blob=embedding.embedding_to_json(vector),
                )
                for paragraph, vector in zip(paragraphs, vectors)
            ]
        )
        db.commit()
        db.refresh(book)
    except HTTPException:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    except EmbeddingUnavailableError:
        db.rollback()
        file_path.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001 - turn storage/DB failures into a clean 500
        db.rollback()
        file_path.unlink(missing_ok=True)
        logger.exception("Upload failed for %s", original_name)
        raise HTTPException(status_code=500, detail="上传失败，请稍后重试") from exc

    return RedirectResponse(url=f"/book/{book.id}", status_code=303)
