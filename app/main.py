from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.database import init_db
from app import models  # noqa: F401 — registers models with Base
from app.routers.upload import router as upload_router
from app.routers.book import router as book_router
from app.routers.comment import router as comment_router
from app.routers.admin import router as admin_router

# Initialise DB at import time so TestClient (no lifespan) also works
init_db()

app = FastAPI(title="SpoilerShield")

@app.on_event("startup")
def startup():
    init_db()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(upload_router)
app.include_router(book_router)
app.include_router(comment_router)
app.include_router(admin_router)


@app.get("/ping")
def ping():
    return {"status": "ok"}
