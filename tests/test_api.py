"""HTTP-level tests for upload, reading, commenting, and moderation."""

from __future__ import annotations

import pytest

from app.config import settings
from app.models import Book, Comment, Paragraph
from app.services.embedding import EmbeddingUnavailableError
from app.services.llm import LLMError


# --------------------------------------------------------------------- basics
def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz(client):
    assert client.get("/healthz").status_code == 200


def test_home_lists_upload_form(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "上传一本书" in response.text


def test_pages_do_not_depend_on_external_assets(client, seeded_book):
    book, _ = seeded_book
    for path in ("/", f"/book/{book.id}", "/admin"):
        html = client.get(path).text
        assert "cdn.tailwindcss.com" not in html
        assert "unpkg.com" not in html
        assert "https://" not in html
        assert "/static/app.css" in html
        assert "/static/app.js" in html


def test_local_assets_are_served(client):
    for path, minimum in (("/static/app.css", 4000), ("/static/app.js", 2000)):
        response = client.get(path)
        assert response.status_code == 200
        assert len(response.text) >= minimum


def test_local_css_has_no_remote_import(client):
    css = client.get("/static/app.css").text
    assert "@import" not in css
    assert "url(http" not in css


# --------------------------------------------------------------------- upload
def test_upload_txt_redirects_to_reader(client, upload_book):
    response = upload_book("第一段。\n\n第二段。\n\n第三段。", title="三体")

    assert response.status_code == 303
    assert response.headers["location"] == "/book/1"

    page = client.get("/book/1")
    assert page.status_code == 200
    assert "三体" in page.text
    assert "第一段。" in page.text


def test_upload_uses_generated_filename_and_keeps_it_inside_upload_dir(
    client, upload_book, tmp_path
):
    response = client.post(
        "/upload",
        files={"file": ("../../evil.txt", b"Para one.\n\nPara two.", "text/plain")},
        data={"title": "Traversal"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    upload_dir = tmp_path / "uploads"
    files = list(upload_dir.iterdir())
    assert len(files) == 1
    assert files[0].name.endswith(".txt")
    assert "evil" not in files[0].name
    assert files[0].parent == upload_dir


def test_upload_rejects_unsupported_extension(client):
    response = client.post(
        "/upload",
        files={"file": ("book.doc", b"whatever", "application/msword")},
        data={"title": "Doc"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "不支持的文件类型" in response.json()["detail"]


def test_upload_can_be_disabled_for_public_demos(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_UPLOADS", False)
    response = client.post(
        "/upload",
        files={"file": ("book.txt", "一。\n\n二。".encode("utf-8"), "text/plain")},
        data={"title": "Demo"},
        follow_redirects=False,
    )
    assert response.status_code == 403
    assert "关闭上传" in response.json()["detail"]


def test_home_hides_the_upload_form_when_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "ALLOW_UPLOADS", False)

    html = client.get("/").text

    assert "关闭上传" in html
    assert 'action="/upload"' not in html


def test_upload_rejects_empty_file(client):
    response = client.post(
        "/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
        data={"title": "Empty"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert "文件为空" in response.json()["detail"]


def test_upload_rejects_corrupt_pdf(client):
    response = client.post(
        "/upload",
        files={"file": ("broken.pdf", b"not a pdf at all", "application/pdf")},
        data={"title": "Broken"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_upload_enforces_size_limit(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0.0005)  # ~512 bytes
    response = client.post(
        "/upload",
        files={"file": ("big.txt", b"x" * 2048, "text/plain")},
        data={"title": "Big"},
        follow_redirects=False,
    )
    assert response.status_code == 413
    assert "MB" in response.json()["detail"]


def test_upload_rejects_too_many_paragraphs(client, monkeypatch):
    monkeypatch.setattr(settings, "MAX_PARAGRAPHS", 2)
    response = client.post(
        "/upload",
        files={"file": ("long.txt", "一。\n\n二。\n\n三。".encode("utf-8"), "text/plain")},
        data={"title": "Long"},
        follow_redirects=False,
    )
    assert response.status_code == 413
    assert "上限" in response.json()["detail"]


def test_upload_embeds_paragraphs_in_a_single_batch(client, upload_book, fake_embedding):
    upload_book("一。\n\n二。\n\n三。")
    assert fake_embedding.batch_calls == 1


def test_upload_returns_503_when_embedding_model_is_unavailable(
    client, fake_embedding, tmp_path
):
    def unavailable(texts):
        raise EmbeddingUnavailableError("本地没有 embedding 模型")

    fake_embedding.encode_batch = unavailable

    response = client.post(
        "/upload",
        files={"file": ("book.txt", "一。\n\n二。".encode("utf-8"), "text/plain")},
        data={"title": "No model"},
        follow_redirects=False,
    )

    assert response.status_code == 503
    assert "embedding" in response.json()["detail"]
    upload_dir = tmp_path / "uploads"
    assert list(upload_dir.iterdir()) == []


def test_upload_falls_back_to_filename_as_title(client, upload_book, db_session):
    upload_book("Only paragraph.", title="")
    book = db_session.query(Book).one()
    assert book.title == "book"


def test_reader_404_for_unknown_book(client):
    assert client.get("/book/999").status_code == 404


# -------------------------------------------------------------------- comments
def _post_comment(client, book_id: int, para_index: int = 0, content: str = "好看"):
    return client.post(
        "/comment",
        data={"book_id": book_id, "para_index": para_index, "content": content},
    )


@pytest.fixture
def seeded_book(book_and_paragraphs):
    return book_and_paragraphs


def test_public_comment_is_visible(client, seeded_book, fake_llm):
    book, _ = seeded_book
    fake_llm.result = {"is_spoiler": False, "confidence": 0.95, "reason": "无剧透"}

    response = _post_comment(client, book.id, content="这段写得很美。")

    assert response.status_code == 200
    assert "这段写得很美。" in response.text
    assert "spoiler-badge" not in response.text


def test_spoiler_comment_is_blurred(client, seeded_book, fake_llm):
    book, _ = seeded_book
    fake_llm.result = {"is_spoiler": True, "confidence": 0.9, "reason": "泄露结局"}

    response = _post_comment(client, book.id, content="凶手其实是管家。")

    assert response.status_code == 200
    assert "spoiler-badge" in response.text
    assert "spoiler-blur" in response.text


def test_low_confidence_comment_goes_to_review_and_text_is_hidden(
    client, seeded_book, fake_llm
):
    book, _ = seeded_book
    fake_llm.result = {"is_spoiler": True, "confidence": 0.3, "reason": "不确定"}

    response = _post_comment(client, book.id, content="我觉得后面他会死。")

    assert response.status_code == 200
    assert "AI 审核中" in response.text
    assert "我觉得后面他会死。" not in response.text


def test_llm_failure_keeps_comment_but_never_publishes_it(
    client, seeded_book, fake_llm, db_session
):
    book, _ = seeded_book
    fake_llm.error = LLMError("connection refused", kind="connection")

    response = _post_comment(client, book.id, content="这段有点拖沓。")

    assert response.status_code == 200
    assert "AI 审核暂不可用" in response.text

    comment = db_session.query(Comment).one()
    assert comment.status == "PENDING_REVIEW"
    assert comment.confidence is None
    assert comment.is_spoiler is None


def test_comment_rejects_empty_content(client, seeded_book):
    book, _ = seeded_book
    response = _post_comment(client, book.id, content="   ")
    assert response.status_code == 400


def test_comment_rejects_too_long_content(client, seeded_book):
    book, _ = seeded_book
    response = _post_comment(client, book.id, content="字" * 501)
    assert response.status_code == 400
    assert "最多" in response.json()["detail"]


def test_comment_404_for_missing_paragraph(client, seeded_book):
    book, _ = seeded_book
    assert _post_comment(client, book.id, para_index=99).status_code == 404


def test_comment_404_for_missing_book(client):
    assert _post_comment(client, book_id=12345).status_code == 404


def test_cross_origin_writes_are_rejected(client, seeded_book):
    book, _ = seeded_book
    response = client.post(
        "/comment",
        data={"book_id": book.id, "para_index": 0, "content": "跨站评论"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    assert "跨站" in response.json()["detail"]


def test_same_origin_writes_are_allowed(client, seeded_book):
    book, _ = seeded_book
    response = client.post(
        "/comment",
        data={"book_id": book.id, "para_index": 0, "content": "同站评论"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200


def test_comment_panel_404_for_missing_paragraph(client, seeded_book):
    book, _ = seeded_book
    assert client.get(f"/book/{book.id}/comments/99").status_code == 404


def test_pending_comments_are_not_counted_in_reader(client, seeded_book, db_session):
    book, paragraphs = seeded_book
    db_session.add(
        Comment(
            paragraph_id=paragraphs[0].id,
            book_id=book.id,
            content="待审",
            status="PENDING_REVIEW",
        )
    )
    db_session.commit()

    page = client.get(f"/book/{book.id}")
    assert page.status_code == 200
    assert "条评论" not in page.text


# ----------------------------------------------------------------------- admin
@pytest.fixture
def pending_comment(seeded_book, db_session):
    book, paragraphs = seeded_book
    comment = Comment(
        paragraph_id=paragraphs[0].id,
        book_id=book.id,
        content="这是一条待审评论",
        status="PENDING_REVIEW",
        is_spoiler=True,
        confidence=0.55,
        ai_reason="可能剧透",
    )
    db_session.add(comment)
    db_session.commit()
    db_session.refresh(comment)
    return comment


def test_admin_lists_pending_comments_with_full_text(client, pending_comment):
    response = client.get("/admin")
    assert response.status_code == 200
    assert "这是一条待审评论" in response.text
    assert "可能剧透" in response.text


def test_admin_approve_publishes_comment(client, pending_comment, db_session):
    response = client.post(
        "/admin/action",
        data={"comment_id": pending_comment.id, "action": "approve"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"

    db_session.expire_all()
    assert db_session.get(Comment, pending_comment.id).status == "PUBLIC"


def test_admin_mark_spoiler(client, pending_comment, db_session):
    client.post(
        "/admin/action",
        data={"comment_id": pending_comment.id, "action": "mark_spoiler"},
        follow_redirects=False,
    )
    db_session.expire_all()
    assert db_session.get(Comment, pending_comment.id).status == "HIDDEN"


def test_admin_delete_comment(client, pending_comment, db_session):
    client.post(
        "/admin/action",
        data={"comment_id": pending_comment.id, "action": "delete"},
        follow_redirects=False,
    )
    db_session.expunge_all()
    assert db_session.query(Comment).filter(Comment.id == pending_comment.id).first() is None


def test_admin_rejects_unknown_action(client, pending_comment):
    response = client.post(
        "/admin/action",
        data={"comment_id": pending_comment.id, "action": "explode"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_admin_action_404_for_missing_comment(client):
    response = client.post(
        "/admin/action",
        data={"comment_id": 424242, "action": "approve"},
        follow_redirects=False,
    )
    assert response.status_code == 404


def test_admin_requires_password_when_configured(client, monkeypatch, pending_comment):
    monkeypatch.setattr(settings, "ADMIN_PASSWORD", "s3cret")
    monkeypatch.setattr(settings, "ADMIN_USER", "admin")

    assert client.get("/admin").status_code == 401
    assert client.get("/admin", auth=("admin", "wrong")).status_code == 401
    assert client.get("/admin", auth=("admin", "s3cret")).status_code == 200


def test_admin_localhost_bypass_is_refused_behind_a_proxy(client, pending_comment):
    # Without ADMIN_PASSWORD a reverse proxy makes every request look local;
    # forwarded headers must not turn that into open access.
    response = client.get("/admin", headers={"X-Forwarded-For": "203.0.113.9"})

    assert response.status_code == 403
    assert "仅允许本机" in response.json()["detail"]


def test_admin_delete_book_removes_file_and_rows(
    client, upload_book, db_session, tmp_path
):
    upload_book("第一段。\n\n第二段。", title="可删书")
    book = db_session.query(Book).one()
    stored = tmp_path / "uploads" / book.filename
    assert stored.exists()

    response = client.post(f"/admin/delete_book/{book.id}", follow_redirects=False)

    assert response.status_code == 303
    db_session.expire_all()
    assert db_session.query(Book).one_or_none() is None
    assert db_session.query(Paragraph).count() == 0
    assert not stored.exists()
