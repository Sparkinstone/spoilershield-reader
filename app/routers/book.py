from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db, templates
from app.models import Book, Paragraph, Comment

router = APIRouter()


@router.get("/")
def home(request: Request, db: Session = Depends(get_db)):
    books = db.query(Book).all()
    return templates.TemplateResponse("index.html", {"request": request, "books": books})


@router.get("/book/{book_id}")
def read_book(request: Request, book_id: int, db: Session = Depends(get_db)):
    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        return {"error": "Book not found"}
    paragraphs = db.query(Paragraph).filter(Paragraph.book_id == book_id).order_by(Paragraph.para_index).all()
    return templates.TemplateResponse("reader.html", {
        "request": request,
        "book": book,
        "paragraphs": paragraphs,
    })


@router.get("/book/{book_id}/comments/{para_index}")
def get_comments(request: Request, book_id: int, para_index: int, db: Session = Depends(get_db)):
    paragraph = db.query(Paragraph).filter(
        Paragraph.book_id == book_id, Paragraph.para_index == para_index
    ).first()
    if not paragraph:
        return {"error": "Paragraph not found"}
    comments = db.query(Comment).filter(Comment.paragraph_id == paragraph.id).all()
    return templates.TemplateResponse("comment_partial.html", {
        "request": request,
        "book_id": book_id,
        "para_index": para_index,
        "comments": comments,
    })
