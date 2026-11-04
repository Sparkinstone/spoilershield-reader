"""Admin panel: moderation queue and book management.

The panel is protected with HTTP Basic auth when ``ADMIN_PASSWORD`` is set.  If
it is not set the panel stays open for local development only; remote requests
are refused rather than silently exposing moderation to the internet.
"""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db, templates
from app.models import Book, Comment

router = APIRouter()
logger = logging.getLogger(__name__)
security = HTTPBasic(auto_error=False)

LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def require_admin(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(security),
) -> None:
    if settings.ADMIN_PASSWORD:
        valid = (
            credentials is not None
            and secrets.compare_digest(
                credentials.username.encode("utf-8"), settings.ADMIN_USER.encode("utf-8")
            )
            and secrets.compare_digest(
                credentials.password.encode("utf-8"),
                settings.ADMIN_PASSWORD.encode("utf-8"),
            )
        )
        if not valid:
            raise HTTPException(
                status_code=401,
                detail="需要管理员登录",
                headers={"WWW-Authenticate": 'Basic realm="SpoilerShield Admin"'},
            )
        return

    host = request.client.host if request.client else ""
    # Behind Nginx/Caddy every request appears to come from 127.0.0.1, which
    # would silently expose the panel without a password. A forwarded header
    # means "there is a proxy in front"; require ADMIN_PASSWORD in that case.
    proxied = bool(
        request.headers.get("x-forwarded-for")
        or request.headers.get("x-real-ip")
        or request.headers.get("forwarded")
    )
    if host not in LOCAL_HOSTS or proxied:
        raise HTTPException(
            status_code=403,
            detail="管理后台未配置 ADMIN_PASSWORD，仅允许本机访问",
        )


@router.get("/admin")
def admin_panel(
    request: Request,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    comments = (
        db.query(Comment)
        .filter(Comment.status == "PENDING_REVIEW")
        .order_by(Comment.id)
        .all()
    )
    books = db.query(Book).order_by(Book.id.desc()).all()
    return templates.TemplateResponse(
        "admin.html", {"request": request, "comments": comments, "books": books}
    )


@router.post("/admin/delete_book/{book_id}")
def delete_book(
    book_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    book = db.query(Book).filter(Book.id == book_id).first()
    if book is None:
        raise HTTPException(status_code=404, detail="书籍不存在")

    file_path = settings.upload_dir / book.filename
    db.delete(book)  # ORM cascades to paragraphs and comments
    db.commit()
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Could not remove uploaded file %s", file_path)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/admin/action")
def admin_action(
    comment_id: int = Form(...),
    action: str = Form(...),
    db: Session = Depends(get_db),
    _: None = Depends(require_admin),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if comment is None:
        raise HTTPException(status_code=404, detail="评论不存在")

    if action == "approve":
        comment.status = "PUBLIC"
        comment.is_spoiler = False
    elif action == "mark_spoiler":
        comment.status = "HIDDEN"
        comment.is_spoiler = True
    elif action == "delete":
        db.delete(comment)
    else:
        raise HTTPException(status_code=400, detail=f"未知操作：{action}")

    db.commit()
    return RedirectResponse(url="/admin", status_code=303)
