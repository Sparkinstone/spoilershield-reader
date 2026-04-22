from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from app.database import get_db, templates
from app.models import Comment

router = APIRouter()


@router.get("/admin")
def admin_panel(request: Request, db: Session = Depends(get_db)):
    comments = db.query(Comment).filter(Comment.status == "PENDING_REVIEW").all()
    return templates.TemplateResponse("admin.html", {"request": request, "comments": comments})


@router.post("/admin/action")
def admin_action(
    request: Request,
    comment_id: int = Form(...),
    action: str = Form(...),
    db: Session = Depends(get_db),
):
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        return {"error": "Comment not found"}

    if action == "approve":
        comment.status = "PUBLIC"
        comment.is_spoiler = False
    elif action == "mark_spoiler":
        comment.status = "HIDDEN"
        comment.is_spoiler = True
    elif action == "delete":
        db.delete(comment)
    else:
        return {"error": "Invalid action"}

    db.commit()

    comments = db.query(Comment).filter(Comment.status == "PENDING_REVIEW").all()
    return templates.TemplateResponse("admin.html", {"request": request, "comments": comments})
