# SpoilerShield MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web app where users upload ebooks, read them paragraph-by-paragraph, comment on paragraphs, and AI automatically detects and hides spoiler comments.

**Architecture:** FastAPI backend with SQLite database, HTMX+Jinja2+Tailwind frontend, sentence-transformers for local embedding, GPT-4o API for spoiler judgment. Single-process deployment — no separate frontend build step.

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy, SQLite, sentence-transformers (all-MiniLM-L6-v2), OpenAI GPT-4o API, HTMX, Jinja2, Tailwind CSS (CDN), PyPDF2, ebooklib, python-dotenv

---

## File Structure

```
CommentMask/
├── .env.example                    # Environment variable template
├── .gitignore                      # Git ignore rules
├── requirements.txt                # Python dependencies
├── generate_test_comments.py       # Batch test comment generator + accuracy report
├── README.md                       # Setup & usage documentation
├── app/
│   ├── __init__.py                 # Package init
│   ├── main.py                     # FastAPI entry point, app factory
│   ├── config.py                   # Settings from .env (threshold, API keys)
│   ├── database.py                 # SQLAlchemy engine, session, init_db()
│   ├── models.py                   # ORM models: Book, Paragraph, Comment
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── upload.py               # POST /upload — file upload + parsing
│   │   ├── book.py                 # GET /book/{book_id} — reader page
│   │   ├── comment.py              # POST /comment — submit + AI detection
│   │   └── admin.py                # GET /admin, POST /admin/action
│   ├── services/
│   │   ├── __init__.py
│   │   ├── parser.py               # PDF/EPUB/TXT → paragraph list
│   │   ├── embedding.py            # sentence-transformers embedding + search
│   │   ├── spoiler_detector.py     # RAG pipeline + LLM spoiler judgment
│   │   └── llm.py                  # OpenAI GPT-4o API call wrapper
│   └── templates/
│   │   ├── base.html               # Jinja2 base layout with Tailwind + HTMX
│   │   ├── index.html              # Upload page (home)
│   │   ├── reader.html             # Reading interface (left: text, right: comments)
│   │   ├── comment_partial.html    # HTMX partial for comment list
│   │   └── admin.html              # Admin panel for pending review
│   └── static/
│       └── style.css               # Minimal custom CSS (blur overlay, etc.)
├── tests/
│   ├── __init__.py
│   ├── test_parser.py              # File parsing tests
│   ├── test_embedding.py           # Embedding + semantic search tests
│   ├── test_spoiler_detector.py    # Spoiler detection pipeline tests
│   ├── test_api.py                 # API endpoint tests
│   └── test_models.py              # ORM model tests
```

---

### Task 1: Project Initialization & Configuration

**Files:**
- Create: `.gitignore`
- Create: `.env.example`
- Create: `requirements.txt`
- Create: `app/__init__.py`
- Create: `app/config.py`

- [ ] **Step 1: Create .gitignore**

```gitignore
__pycache__/
*.pyc
.env
venv/
*.db
*.sqlite3
uploads/
instance/
dist/
build/
*.egg-info/
```

- [ ] **Step 2: Create .env.example**

```
OPENAI_API_KEY=sk-your-key-here
OPENAI_API_BASE=https://api.openai.com/v1
SPOILER_CONFIDENCE_THRESHOLD=0.7
LLM_MODEL=gpt-4o
EMBEDDING_MODEL=all-MiniLM-L6-v2
DATABASE_URL=sqlite:///./spoiler_shield.db
```

- [ ] **Step 3: Create requirements.txt**

```
fastapi==0.115.6
uvicorn==0.34.0
sqlalchemy==2.0.36
python-dotenv==1.0.1
pypdf2==3.0.1
ebooklib==0.18
openai==1.58.1
sentence-transformers==3.3.1
jinja2==3.1.4
python-multipart==0.0.20
httpx==0.28.1
pytest==8.3.4
```

- [ ] **Step 4: Create app/__init__.py** (empty)

```python
```

- [ ] **Step 5: Create app/config.py**

```python
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_API_BASE: str = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    SPOILER_CONFIDENCE_THRESHOLD: float = float(os.getenv("SPOILER_CONFIDENCE_THRESHOLD", "0.7"))
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gpt-4o")
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./spoiler_shield.db")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "uploads")


settings = Settings()
```

- [ ] **Step 6: Create uploads directory placeholder**

Run: `mkdir -p uploads`

- [ ] **Step 7: Install dependencies and verify**

Run: `pip install -r requirements.txt`
Expected: All packages install successfully.

- [ ] **Step 8: Commit**

```bash
git init
git add .gitignore .env.example requirements.txt app/__init__.py app/config.py
git commit -m "feat: project initialization with config and dependencies"
```

---

### Task 2: Database Models & Initialization

**Files:**
- Create: `app/database.py`
- Create: `app/models.py`
- Create: `tests/__init__.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing test for models**

```python
# tests/test_models.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, init_db
from app.models import Book, Paragraph, Comment


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_create_book(db_session):
    book = Book(title="Test Book", filename="test.pdf", total_paragraphs=10)
    db_session.add(book)
    db_session.commit()
    assert book.id is not None
    assert book.title == "Test Book"


def test_create_paragraph(db_session):
    book = Book(title="Test Book", filename="test.pdf", total_paragraphs=1)
    db_session.add(book)
    db_session.commit()
    para = Paragraph(book_id=book.id, para_index=0, page_num=1, content="Hello world")
    db_session.add(para)
    db_session.commit()
    assert para.id is not None
    assert para.content == "Hello world"


def test_create_comment(db_session):
    book = Book(title="Test Book", filename="test.pdf", total_paragraphs=1)
    db_session.add(book)
    db_session.commit()
    para = Paragraph(book_id=book.id, para_index=0, page_num=1, content="Hello world")
    db_session.add(para)
    db_session.commit()
    comment = Comment(
        paragraph_id=para.id,
        content="Great paragraph!",
        status="PUBLIC",
        is_spoiler=False,
        confidence=0.95,
        ai_reason="No spoiler content detected."
    )
    db_session.add(comment)
    db_session.commit()
    assert comment.id is not None
    assert comment.status == "PUBLIC"
    assert comment.is_spoiler is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL — `app.database` and `app.models` modules don't exist yet.

- [ ] **Step 3: Create app/models.py**

```python
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)  # pdf, epub, txt
    total_paragraphs = Column(Integer, default=0)

    paragraphs = relationship("Paragraph", back_populates="book", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="book", cascade="all, delete-orphan")


class Paragraph(Base):
    __tablename__ = "paragraphs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    para_index = Column(Integer, nullable=False)
    page_num = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    embedding_blob = Column(Text, nullable=True)  # JSON-serialized embedding vector

    book = relationship("Book", back_populates="paragraphs")


class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    paragraph_id = Column(Integer, ForeignKey("paragraphs.id"), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id"), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="PENDING_REVIEW")  # PENDING_REVIEW, PUBLIC, HIDDEN
    is_spoiler = Column(Boolean, default=None)
    confidence = Column(Float, default=None)
    ai_reason = Column(Text, default=None)

    paragraph = relationship("Paragraph")
    book = relationship("Book", back_populates="comments")
```

- [ ] **Step 4: Create app/database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(settings.DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(engine)
```

- [ ] **Step 5: Create tests/__init__.py** (empty)

```python
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/database.py app/models.py tests/__init__.py tests/test_models.py
git commit -m "feat: database models and initialization"
```

---

### Task 3: File Parser Service

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write failing tests for parser**

```python
# tests/test_parser.py
import pytest
from app.services.parser import parse_file, parse_txt, parse_pdf, parse_epub


def test_parse_txt():
    content = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
    result = parse_txt(content)
    assert len(result) == 3
    assert result[0]["content"] == "Paragraph one."
    assert result[0]["para_index"] == 0
    assert result[1]["para_index"] == 1


def test_parse_txt_empty_lines():
    content = "Para 1.\n\n\n\nPara 2.\n\n\nPara 3."
    result = parse_txt(content)
    assert len(result) == 3


def test_parse_txt_single_paragraph():
    content = "Just one paragraph with no breaks."
    result = parse_txt(content)
    assert len(result) == 1
    assert result[0]["content"] == "Just one paragraph with no breaks."


def test_parse_file_txt(tmp_path):
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Para one.\n\nPara two.")
    result = parse_file(str(txt_file), "txt")
    assert len(result) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL — `app.services.parser` module doesn't exist.

- [ ] **Step 3: Create app/services/__init__.py** (empty)

```python
```

- [ ] **Step 4: Create app/services/parser.py**

```python
import os
from PyPDF2 import PdfReader
import ebooklib
from ebooklib import epub


def parse_txt(content: str) -> list[dict]:
    """Split TXT content into paragraphs by double newlines."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    return [
        {"para_index": i, "page_num": None, "content": para}
        for i, para in enumerate(paragraphs)
    ]


def parse_pdf(file_path: str) -> list[dict]:
    """Extract paragraphs from PDF, tracking page numbers."""
    reader = PdfReader(file_path)
    paragraphs = []
    para_index = 0
    for page_num, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        page_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        for para in page_paragraphs:
            paragraphs.append({
                "para_index": para_index,
                "page_num": page_num,
                "content": para,
            })
            para_index += 1
    return paragraphs


def parse_epub(file_path: str) -> list[dict]:
    """Extract paragraphs from EPUB."""
    book = epub.read_epub(file_path)
    paragraphs = []
    para_index = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        import re
        html_content = item.get_content().decode("utf-8", errors="ignore")
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", "\n", html_content)
        page_paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        # Also split by single newlines if double-newline split yields nothing
        if not page_paragraphs:
            page_paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
        for para in page_paragraphs:
            if len(para) < 10:
                continue  # Skip very short fragments (likely HTML artifacts)
            paragraphs.append({
                "para_index": para_index,
                "page_num": None,
                "content": para,
            })
            para_index += 1
    return paragraphs


def parse_file(file_path: str, file_type: str) -> list[dict]:
    """Parse a book file into a list of paragraph dicts."""
    if file_type == "txt":
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        return parse_txt(content)
    elif file_type == "pdf":
        return parse_pdf(file_path)
    elif file_type == "epub":
        return parse_epub(file_path)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_parser.py -v`
Expected: All 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/__init__.py app/services/parser.py tests/test_parser.py
git commit -m "feat: file parser service for PDF, EPUB, TXT"
```

---

### Task 4: Embedding Service

**Files:**
- Create: `app/services/embedding.py`
- Create: `tests/test_embedding.py`

- [ ] **Step 1: Write failing tests for embedding service**

```python
# tests/test_embedding.py
import pytest
import json
from app.services.embedding import EmbeddingService


@pytest.fixture
def embedding_service():
    return EmbeddingService()


def test_generate_embedding(embedding_service):
    text = "This is a test paragraph."
    vector = embedding_service.generate_embedding(text)
    assert isinstance(vector, list)
    assert len(vector) > 0
    assert all(isinstance(v, float) for v in vector)


def test_embedding_to_json(embedding_service):
    vector = [0.1, 0.2, 0.3]
    json_str = embedding_service.embedding_to_json(vector)
    assert isinstance(json_str, str)
    parsed = json.loads(json_str)
    assert parsed == vector


def test_json_to_embedding(embedding_service):
    json_str = "[0.1, 0.2, 0.3]"
    vector = embedding_service.json_to_embedding(json_str)
    assert vector == [0.1, 0.2, 0.3]


def test_semantic_search(embedding_service):
    paragraphs = [
        {"para_index": 0, "content": "The detective arrived at the crime scene."},
        {"para_index": 1, "content": "It was a rainy day in the city."},
        {"para_index": 2, "content": "The murderer was revealed to be the butler."},
    ]
    query = "Who committed the crime?"
    results = embedding_service.semantic_search(query, paragraphs, top_k=2)
    assert len(results) <= 2
    assert isinstance(results[0], dict)
    assert "para_index" in results[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_embedding.py -v`
Expected: FAIL — `app.services.embedding` module doesn't exist.

- [ ] **Step 3: Create app/services/embedding.py**

```python
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from app.config import settings


class EmbeddingService:
    def __init__(self, model_name: str = None):
        model_name = model_name or settings.EMBEDDING_MODEL
        self.model = SentenceTransformer(model_name)

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for a text string."""
        vector = self.model.encode(text)
        return vector.tolist()

    def embedding_to_json(self, vector: list[float]) -> str:
        """Serialize embedding vector to JSON string for DB storage."""
        return json.dumps(vector)

    def json_to_embedding(self, json_str: str) -> list[float]:
        """Deserialize JSON string back to embedding vector."""
        return json.loads(json_str)

    def semantic_search(
        self, query: str, paragraphs: list[dict], top_k: int = 3
    ) -> list[dict]:
        """Find the top_k most semantically similar paragraphs to the query."""
        if not paragraphs:
            return []

        para_texts = [p["content"] for p in paragraphs]
        query_embedding = self.model.encode(query)
        para_embeddings = self.model.encode(para_texts)

        similarities = np.dot(para_embeddings, query_embedding) / (
            np.linalg.norm(para_embeddings, axis=1) * np.linalg.norm(query_embedding)
        )

        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            para = paragraphs[idx]
            results.append({
                "para_index": para["para_index"],
                "content": para["content"],
                "similarity": float(similarities[idx]),
            })
        return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_embedding.py -v`
Expected: All 4 tests PASS. (Note: first run will download the embedding model ~90MB)

- [ ] **Step 5: Commit**

```bash
git add app/services/embedding.py tests/test_embedding.py
git commit -m "feat: embedding service with semantic search"
```

---

### Task 5: LLM Service & Spoiler Detector

**Files:**
- Create: `app/services/llm.py`
- Create: `app/services/spoiler_detector.py`
- Create: `tests/test_spoiler_detector.py`

- [ ] **Step 1: Write failing tests for spoiler detector**

```python
# tests/test_spoiler_detector.py
import pytest
from unittest.mock import MagicMock, patch
from app.services.spoiler_detector import SpoilerDetector


@pytest.fixture
def mock_embedding_service():
    service = MagicMock()
    service.semantic_search.return_value = [
        {"para_index": 5, "content": "The butler was the murderer.", "similarity": 0.85},
        {"para_index": 10, "content": "The detective solved the case.", "similarity": 0.72},
        {"para_index": 0, "content": "A crime was committed.", "similarity": 0.60},
    ]
    return service


@pytest.fixture
def mock_llm_service():
    service = MagicMock()
    service.judge_spoiler.return_value = {
        "is_spoiler": True,
        "confidence": 0.85,
        "reason": "Comment reveals the killer's identity from page 50.",
    }
    return service


def test_detect_spoiler_with_future_paragraphs(mock_embedding_service, mock_llm_service):
    detector = SpoilerDetector(mock_embedding_service, mock_llm_service)
    result = detector.detect(
        comment="The butler did it!",
        current_para_index=2,
        all_paragraphs=[{"para_index": i, "content": f"Para {i}"} for i in range(15)],
    )
    assert result["is_spoiler"] is True
    assert result["confidence"] == 0.85


def test_detect_no_future_paragraphs(mock_embedding_service, mock_llm_service):
    """When no relevant future paragraphs exist, LLM is still called but with empty future context."""
    mock_embedding_service.semantic_search.return_value = [
        {"para_index": 0, "content": "A crime was committed.", "similarity": 0.60},
        {"para_index": 1, "content": "The detective arrived.", "similarity": 0.55},
    ]
    detector = SpoilerDetector(mock_embedding_service, mock_llm_service)
    result = detector.detect(
        comment="Interesting start!",
        current_para_index=5,
        all_paragraphs=[{"para_index": i, "content": f"Para {i}"} for i in range(15)],
    )
    # LLM called with no future paragraphs — should return non-spoiler
    mock_llm_service.judge_spoiler.assert_called_once()


def test_determine_status_high_confidence_spoiler():
    from app.services.spoiler_detector import determine_status
    assert determine_status(True, 0.85) == "HIDDEN"


def test_determine_status_high_confidence_non_spoiler():
    from app.services.spoiler_detector import determine_status
    assert determine_status(False, 0.85) == "PUBLIC"


def test_determine_status_low_confidence():
    from app.services.spoiler_detector import determine_status
    assert determine_status(True, 0.5) == "PENDING_REVIEW"
    assert determine_status(False, 0.5) == "PENDING_REVIEW"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_spoiler_detector.py -v`
Expected: FAIL — modules don't exist.

- [ ] **Step 3: Create app/services/llm.py**

```python
import json
from openai import OpenAI
from app.config import settings


class LLMService:
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.OPENAI_API_KEY,
            base_url=settings.OPENAI_API_BASE,
        )

    def judge_spoiler(
        self,
        comment: str,
        current_paragraph: str,
        future_paragraphs: list[str],
    ) -> dict:
        """Call GPT-4o to judge if a comment is a spoiler.

        Returns dict with keys: is_spoiler, confidence, reason.
        """
        future_text = "\n".join(
            f"- {para}" for para in future_paragraphs
        ) if future_paragraphs else "No relevant future paragraphs found."

        prompt = f"""You are a spoiler detection AI for a book reading platform.

A reader posted a comment on paragraph at position in the book. Your job is to determine if this comment reveals information about events that happen AFTER the current paragraph.

**Current paragraph (the one being commented on):**
{current_paragraph}

**Relevant paragraphs that appear LATER in the book:**
{future_text}

**The reader's comment:**
{comment}

Analyze whether this comment contains spoiler information about future events in the book. A spoiler is any information that reveals plot developments, character fates, or surprises that occur after the current paragraph.

Respond with ONLY a JSON object (no other text):
```json
{{"is_spoiler": true/false, "confidence": 0.0-1.0, "reason": "explanation"}}
```"""

        response = self.client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()
        # Extract JSON from response (may be wrapped in markdown code block)
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()

        result = json.loads(content)
        return {
            "is_spoiler": bool(result.get("is_spoiler", False)),
            "confidence": float(result.get("confidence", 0.0)),
            "reason": str(result.get("reason", "")),
        }
```

- [ ] **Step 4: Create app/services/spoiler_detector.py**

```python
from app.config import settings


def determine_status(is_spoiler: bool, confidence: float) -> str:
    """Determine comment status based on AI judgment and confidence threshold."""
    threshold = settings.SPOILER_CONFIDENCE_THRESHOLD
    if confidence >= threshold:
        if is_spoiler:
            return "HIDDEN"
        else:
            return "PUBLIC"
    else:
        return "PENDING_REVIEW"


class SpoilerDetector:
    def __init__(self, embedding_service, llm_service):
        self.embedding_service = embedding_service
        self.llm_service = llm_service

    def detect(
        self,
        comment: str,
        current_para_index: int,
        all_paragraphs: list[dict],
    ) -> dict:
        """Run the full spoiler detection pipeline.

        1. Semantic search to find 3 most relevant paragraphs
        2. Filter for paragraphs that come AFTER current_para_index
        3. Call LLM to judge if comment is a spoiler
        4. Determine comment status

        Returns dict with: is_spoiler, confidence, reason, status
        """
        # Step 1: Semantic search
        relevant = self.embedding_service.semantic_search(comment, all_paragraphs, top_k=3)

        # Step 2: Filter for future paragraphs
        future_paragraphs = [
            p for p in relevant if p["para_index"] > current_para_index
        ]

        # Get current paragraph content
        current_para = None
        for p in all_paragraphs:
            if p["para_index"] == current_para_index:
                current_para = p["content"]
                break

        if current_para is None:
            current_para = ""

        # Step 3: Call LLM
        future_contents = [p["content"] for p in future_paragraphs]
        llm_result = self.llm_service.judge_spoiler(
            comment=comment,
            current_paragraph=current_para,
            future_paragraphs=future_contents,
        )

        # Step 4: Determine status
        status = determine_status(llm_result["is_spoiler"], llm_result["confidence"])

        return {
            "is_spoiler": llm_result["is_spoiler"],
            "confidence": llm_result["confidence"],
            "reason": llm_result["reason"],
            "status": status,
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_spoiler_detector.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/llm.py app/services/spoiler_detector.py tests/test_spoiler_detector.py
git commit -m "feat: LLM service and spoiler detection pipeline"
```

---

### Task 6: FastAPI App Entry & Upload Router

**Files:**
- Create: `app/main.py`
- Create: `app/routers/__init__.py`
- Create: `app/routers/upload.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing tests for upload endpoint**

```python
# tests/test_api.py
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_ping(client):
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_txt(client, tmp_path):
    txt_file = tmp_path / "test.txt"
    txt_file.write_text("Para one.\n\nPara two.\n\nPara three.")
    with open(str(txt_file), "rb") as f:
        response = client.post("/upload", files={"file": ("test.txt", f, "text/plain")}, data={"title": "Test Book"})
    assert response.status_code == 200
    data = response.json()
    assert "book_id" in data
    assert data["total_paragraphs"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_api.py -v`
Expected: FAIL — `app.main` module doesn't exist.

- [ ] **Step 3: Create app/routers/__init__.py** (empty)

```python
```

- [ ] **Step 4: Create app/routers/upload.py**

```python
import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
from app.database import get_db, init_db
from app.models import Book, Paragraph
from app.services.parser import parse_file
from app.services.embedding import EmbeddingService
from app.config import settings

router = APIRouter()
embedding_service = None  # Lazy init to avoid loading model at import time


def get_embedding_service():
    global embedding_service
    if embedding_service is None:
        embedding_service = EmbeddingService()
    return embedding_service


@router.post("/upload")
async def upload_book(
    file: UploadFile = File(...),
    title: str = Form(...),
    db: Session = Depends(get_db),
):
    # Determine file type from extension
    filename = file.filename
    file_type = filename.rsplit(".", 1)[-1].lower()
    if file_type not in ("pdf", "epub", "txt"):
        return {"error": f"Unsupported file type: {file_type}"}

    # Save uploaded file
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Parse file into paragraphs
    paragraphs = parse_file(file_path, file_type)

    # Create book record
    book = Book(title=title, filename=filename, file_type=file_type, total_paragraphs=len(paragraphs))
    db.add(book)
    db.commit()
    db.refresh(book)

    # Generate embeddings and store paragraphs
    emb_service = get_embedding_service()
    for para in paragraphs:
        embedding_vector = emb_service.generate_embedding(para["content"])
        embedding_json = emb_service.embedding_to_json(embedding_vector)
        p = Paragraph(
            book_id=book.id,
            para_index=para["para_index"],
            page_num=para.get("page_num"),
            content=para["content"],
            embedding_blob=embedding_json,
        )
        db.add(p)
    db.commit()

    return {"book_id": book.id, "title": book.title, "total_paragraphs": len(paragraphs)}
```

- [ ] **Step 5: Create app/main.py**

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.database import init_db
from app.routers.upload import router as upload_router
from app.routers.book import router as book_router
from app.routers.comment import router as comment_router
from app.routers.admin import router as admin_router

app = FastAPI(title="SpoilerShield")

# Initialize database on startup
@app.on_event("startup")
def startup():
    init_db()

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Include routers
app.include_router(upload_router)
app.include_router(book_router)
app.include_router(comment_router)
app.include_router(admin_router)


@app.get("/ping")
def ping():
    return {"status": "ok"}
```

- [ ] **Step 6: Create app/static/style.css** (minimal placeholder for now)

```css
.spoiler-blur {
    filter: blur(5px);
    transition: filter 0.3s ease;
}
.spoiler-blur.revealed {
    filter: none;
}
.spoiler-overlay {
    position: relative;
}
.spoiler-overlay .overlay-text {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: rgba(0,0,0,0.7);
    color: white;
    padding: 4px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.85rem;
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_api.py -v`
Expected: Both tests PASS.

- [ ] **Step 8: Commit**

```bash
git add app/main.py app/routers/__init__.py app/routers/upload.py app/static/style.css tests/test_api.py
git commit -m "feat: FastAPI app entry point and upload router"
```

---

### Task 7: Book Reader Router & Templates

**Files:**
- Create: `app/routers/book.py`
- Create: `app/templates/base.html`
- Create: `app/templates/index.html`
- Create: `app/templates/reader.html`
- Create: `app/templates/comment_partial.html`

- [ ] **Step 1: Create app/templates/base.html**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}SpoilerShield{% endblock %}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@2.0.4"></script>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body class="bg-gray-50 min-h-screen">
    <nav class="bg-white shadow px-6 py-3 flex items-center justify-between">
        <a href="/" class="text-xl font-bold text-indigo-600">SpoilerShield</a>
        <div class="flex gap-4">
            <a href="/admin" class="text-gray-600 hover:text-indigo-600">Admin Panel</a>
        </div>
    </nav>
    <main class="max-w-7xl mx-auto px-4 py-6">
        {% block content %}{% endblock %}
    </main>
</body>
</html>
```

- [ ] **Step 2: Create app/templates/index.html**

```html
{% extends "base.html" %}
{% block title %}SpoilerShield - Upload{% endblock %}
{% block content %}
<div class="max-w-md mx-auto mt-10">
    <h1 class="text-2xl font-bold mb-6 text-center">Upload a Book</h1>
    <form action="/upload" method="post" enctype="multipart/form-data"
          class="bg-white shadow rounded-lg p-6 space-y-4">
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">Book Title</label>
            <input type="text" name="title" required
                   class="w-full border rounded px-3 py-2 focus:ring-indigo-500 focus:border-indigo-500">
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">File (PDF, EPUB, TXT)</label>
            <input type="file" name="file" accept=".pdf,.epub,.txt" required
                   class="w-full border rounded px-3 py-2">
        </div>
        <button type="submit"
                class="w-full bg-indigo-600 text-white rounded px-4 py-2 hover:bg-indigo-700">
            Upload & Parse
        </button>
    </form>
    {% if books %}
    <div class="mt-8">
        <h2 class="text-lg font-semibold mb-3">Your Books</h2>
        <ul class="space-y-2">
            {% for book in books %}
            <li class="bg-white shadow rounded p-3 flex justify-between items-center">
                <span>{{ book.title }} ({{ book.file_type }})</span>
                <a href="/book/{{ book.id }}" class="text-indigo-600 hover:underline">Read</a>
            </li>
            {% endfor %}
        </ul>
    </div>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 3: Create app/templates/reader.html**

```html
{% extends "base.html" %}
{% block title %}SpoilerShield - {{ book.title }}{% endblock %}
{% block content %}
<div class="flex gap-6 h-[calc(100vh-80px)]">
    <!-- Left: Book text -->
    <div class="w-1/2 overflow-y-auto bg-white shadow rounded-lg p-6" id="book-text">
        <h2 class="text-xl font-bold mb-4">{{ book.title }}</h2>
        <div id="paragraphs">
            {% for para in paragraphs %}
            <div class="paragraph-block mb-4 p-3 rounded cursor-pointer hover:bg-indigo-50 transition"
                 id="para-{{ para.para_index }}"
                 hx-get="/book/{{ book.id }}/comments/{{ para.para_index }}"
                 hx-target="#comment-sidebar"
                 hx-swap="innerHTML"
                 onclick="selectParagraph({{ para.para_index }})">
                {% if para.page_num %}
                <span class="text-xs text-gray-400 mr-2">p.{{ para.page_num }}</span>
                {% endif %}
                <span class="text-sm text-gray-500 mr-2">[{{ para.para_index }}]</span>
                <p class="text-gray-800 leading-relaxed">{{ para.content }}</p>
            </div>
            {% endfor %}
        </div>
    </div>

    <!-- Right: Comment sidebar -->
    <div class="w-1/2 overflow-y-auto bg-white shadow rounded-lg p-6" id="comment-sidebar">
        <div class="text-center text-gray-400 mt-20">
            <p>Click a paragraph to see comments</p>
        </div>
    </div>
</div>

<!-- Global spoiler toggle -->
<div class="fixed bottom-4 right-4">
    <button id="spoiler-toggle" onclick="toggleAllSpoilers()"
            class="bg-gray-800 text-white px-4 py-2 rounded shadow hover:bg-gray-700">
        Show All Spoilers
    </button>
</div>

<script>
let selectedParaIndex = null;
let spoilersVisible = false;

function selectParagraph(index) {
    selectedParaIndex = index;
    // Highlight selected paragraph
    document.querySelectorAll('.paragraph-block').forEach(el => el.classList.remove('bg-indigo-100'));
    document.getElementById('para-' + index).classList.add('bg-indigo-100');
}

function toggleAllSpoilers() {
    spoilersVisible = !spoilersVisible;
    const btn = document.getElementById('spoiler-toggle');
    btn.textContent = spoilersVisible ? 'Hide All Spoilers' : 'Show All Spoilers';
    document.querySelectorAll('.spoiler-blur').forEach(el => {
        if (spoilersVisible) {
            el.classList.add('revealed');
        } else {
            el.classList.remove('revealed');
        }
    });
    document.querySelectorAll('.overlay-text').forEach(el => {
        el.style.display = spoilersVisible ? 'none' : '';
    });
}

function revealSpoiler(el) {
    el.parentElement.querySelector('.spoiler-blur').classList.add('revealed');
    el.style.display = 'none';
}
</script>
{% endblock %}
```

- [ ] **Step 4: Create app/templates/comment_partial.html**

```html
<div>
    <h3 class="text-lg font-semibold mb-2">
        Comments on Paragraph {{ para_index }}
    </h3>

    <!-- Comment list -->
    <div id="comment-list" class="space-y-3 mb-6">
        {% for comment in comments %}
        <div class="border rounded p-3">
            {% if comment.status == "HIDDEN" %}
            <div class="spoiler-overlay">
                <div class="spoiler-blur">{{ comment.content }}</div>
                <span class="overlay-text" onclick="revealSpoiler(this)">Click to reveal spoiler</span>
            </div>
            <div class="mt-1 text-xs text-red-500">
                AI: spoiler (confidence: {{ comment.confidence }}) — {{ comment.ai_reason }}
            </div>
            {% elif comment.status == "PENDING_REVIEW" %}
            <div class="bg-yellow-50 border-yellow-200 rounded p-2">
                <p class="text-yellow-800">{{ comment.content }}</p>
                <p class="text-xs text-yellow-600 mt-1">
                    Pending review (confidence: {{ comment.confidence }}) — {{ comment.ai_reason }}
                </p>
            </div>
            {% else %}
            <p class="text-gray-800">{{ comment.content }}</p>
            {% endif %}
        </div>
        {% endfor %}
        {% if not comments %}
        <p class="text-gray-400 text-sm">No comments yet.</p>
        {% endif %}
    </div>

    <!-- Add comment form -->
    {% if selected_para_index is not None %}
    <form hx-post="/comment" hx-target="#comment-sidebar" hx-swap="innerHTML"
          class="space-y-3">
        <input type="hidden" name="book_id" value="{{ book_id }}">
        <input type="hidden" name="para_index" value="{{ para_index }}">
        <textarea name="content" rows="3" required
                  class="w-full border rounded px-3 py-2 focus:ring-indigo-500"
                  placeholder="Write your comment..."></textarea>
        <button type="submit"
                class="bg-indigo-600 text-white rounded px-4 py-2 hover:bg-indigo-700">
            Post Comment
        </button>
    </form>
    {% endif %}
</div>
```

- [ ] **Step 5: Create app/routers/book.py**

```python
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
        "selected_para_index": para_index,
    })
```

- [ ] **Step 6: Verify app starts**

Run: `cd D:/Learn/workshop/CommentMask && python -c "from app.main import app; print('App loaded OK')"`
Expected: "App loaded OK"

- [ ] **Step 7: Commit**

```bash
git add app/routers/book.py app/templates/base.html app/templates/index.html app/templates/reader.html app/templates/comment_partial.html
git commit -m "feat: book reader router and HTML templates"
```

---

### Task 8: Comment Router with AI Detection

**Files:**
- Create: `app/routers/comment.py`

- [ ] **Step 1: Create app/routers/comment.py**

```python
from fastapi import APIRouter, Depends, Request, Form
from sqlalchemy.orm import Session
from app.database import get_db, templates
from app.models import Book, Paragraph, Comment
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.spoiler_detector import SpoilerDetector

router = APIRouter()

embedding_service = None
llm_service = None


def get_detector():
    global embedding_service, llm_service
    if embedding_service is None:
        embedding_service = EmbeddingService()
    if llm_service is None:
        llm_service = LLMService()
    return SpoilerDetector(embedding_service, llm_service)


@router.post("/comment")
def post_comment(
    request: Request,
    book_id: int = Form(...),
    para_index: int = Form(...),
    content: str = Form(...),
    db: Session = Depends(get_db),
):
    # Get the paragraph being commented on
    paragraph = db.query(Paragraph).filter(
        Paragraph.book_id == book_id, Paragraph.para_index == para_index
    ).first()
    if not paragraph:
        return {"error": "Paragraph not found"}

    # Get all paragraphs for semantic search
    all_paragraphs = db.query(Paragraph).filter(Paragraph.book_id == book_id).order_by(Paragraph.para_index).all()
    para_dicts = [{"para_index": p.para_index, "content": p.content} for p in all_paragraphs]

    # Run spoiler detection
    detector = get_detector()
    result = detector.detect(
        comment=content,
        current_para_index=para_index,
        all_paragraphs=para_dicts,
    )

    # Save comment
    comment = Comment(
        paragraph_id=paragraph.id,
        book_id=book_id,
        content=content,
        status=result["status"],
        is_spoiler=result["is_spoiler"],
        confidence=result["confidence"],
        ai_reason=result["reason"],
    )
    db.add(comment)
    db.commit()

    # Return updated comment list
    comments = db.query(Comment).filter(Comment.paragraph_id == paragraph.id).all()
    return templates.TemplateResponse("comment_partial.html", {
        "request": request,
        "book_id": book_id,
        "para_index": para_index,
        "comments": comments,
        "selected_para_index": para_index,
    })
```

- [ ] **Step 2: Verify module imports correctly**

Run: `python -c "from app.routers.comment import router; print('Comment router OK')"`
Expected: "Comment router OK"

- [ ] **Step 3: Commit**

```bash
git add app/routers/comment.py
git commit -m "feat: comment submission with AI spoiler detection"
```

---

### Task 9: Admin Router & Template

**Files:**
- Create: `app/routers/admin.py`
- Create: `app/templates/admin.html`

- [ ] **Step 1: Create app/templates/admin.html**

```html
{% extends "base.html" %}
{% block title %}SpoilerShield - Admin{% endblock %}
{% block content %}
<div class="max-w-4xl mx-auto mt-6">
    <h1 class="text-2xl font-bold mb-6">Admin Panel — Pending Review Comments</h1>

    {% if comments %}
    <div class="space-y-4">
        {% for comment in comments %}
        <div class="bg-white shadow rounded-lg p-4">
            <div class="flex justify-between items-start mb-2">
                <span class="text-sm text-gray-500">
                    Book: {{ comment.book.title }} | Paragraph #{{ comment.paragraph.para_index }}
                </span>
                <span class="text-xs px-2 py-1 rounded bg-yellow-100 text-yellow-800">
                    Pending Review
                </span>
            </div>

            <p class="text-gray-800 mb-2">{{ comment.content }}</p>

            <div class="bg-gray-50 rounded p-2 mb-3 text-sm">
                <p><strong>AI Judgment:</strong> {{ "Spoiler" if comment.is_spoiler else "Non-spoiler" }}</p>
                <p><strong>Confidence:</strong> {{ comment.confidence }}</p>
                <p><strong>Reason:</strong> {{ comment.ai_reason }}</p>
            </div>

            <div class="flex gap-2">
                <form hx-post="/admin/action" hx-target="#admin-results" hx-swap="innerHTML"
                      class="inline">
                    <input type="hidden" name="comment_id" value="{{ comment.id }}">
                    <input type="hidden" name="action" value="approve">
                    <button type="submit" class="bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700">
                        Approve (Public)
                    </button>
                </form>
                <form hx-post="/admin/action" hx-target="#admin-results" hx-swap="innerHTML"
                      class="inline">
                    <input type="hidden" name="comment_id" value="{{ comment.id }}">
                    <input type="hidden" name="action" value="mark_spoiler">
                    <button type="submit" class="bg-red-600 text-white px-3 py-1 rounded hover:bg-red-700">
                        Mark as Spoiler
                    </button>
                </form>
                <form hx-post="/admin/action" hx-target="#admin-results" hx-swap="innerHTML"
                      class="inline">
                    <input type="hidden" name="comment_id" value="{{ comment.id }}">
                    <input type="hidden" name="action" value="delete">
                    <button type="submit" class="bg-gray-600 text-white px-3 py-1 rounded hover:bg-gray-700">
                        Delete
                    </button>
                </form>
            </div>
        </div>
        {% endfor %}
    </div>
    {% else %}
    <p class="text-gray-400 text-center mt-10">No pending review comments.</p>
    {% endif %}
</div>
{% endblock %}
```

- [ ] **Step 2: Create app/routers/admin.py**

```python
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

    # Return updated admin panel
    comments = db.query(Comment).filter(Comment.status == "PENDING_REVIEW").all()
    return templates.TemplateResponse("admin.html", {"request": request, "comments": comments})
```

- [ ] **Step 3: Verify module imports correctly**

Run: `python -c "from app.routers.admin import router; print('Admin router OK')"`
Expected: "Admin router OK"

- [ ] **Step 4: Commit**

```bash
git add app/routers/admin.py app/templates/admin.html
git commit -m "feat: admin panel for reviewing pending comments"
```

---

### Task 10: Test Comment Generator & Accuracy Report

**Files:**
- Create: `generate_test_comments.py`

- [ ] **Step 1: Create generate_test_comments.py**

```python
"""
SpoilerShield Test Comment Generator & Accuracy Report

Usage:
    python generate_test_comments.py --book-id 1 --num-comments 100 --spoiler-ratio 0.3

This script:
1. Batch inserts mock comments into a specified book
2. Each comment is labeled as spoiler or non-spoiler with preset ground truth
3. Triggers AI spoiler detection for each comment
4. Generates an accuracy report comparing AI judgments vs ground truth labels
"""
import argparse
import sys
import os
import random

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal, init_db
from app.models import Book, Paragraph, Comment
from app.services.embedding import EmbeddingService
from app.services.llm import LLMService
from app.services.spoiler_detector import SpoilerDetector


# Predefined comment templates
SPOILER_COMMENTS = [
    "The main character dies at the end.",
    "The villain is actually the protagonist's father.",
    "The treasure was hidden in the cave all along.",
    "She betrays him in the final chapter.",
    "The butler is the murderer.",
    "They get married in the epilogue.",
    "The kingdom falls in the last battle.",
    "He sacrifices himself to save everyone.",
    "The secret letter reveals the truth.",
    "The real culprit was the detective's partner.",
]

NON_SPOILER_COMMENTS = [
    "This paragraph is beautifully written.",
    "I really enjoyed the descriptive language here.",
    "The author's style is very engaging.",
    "This reminds me of a similar scene in another book.",
    "Great character development in this section.",
    "The pacing of this part is excellent.",
    "I love the imagery used here.",
    "This is one of my favorite paragraphs.",
    "The dialogue here feels very natural.",
    "The atmosphere in this section is compelling.",
]


def generate_comments(book_id: int, num_comments: int, spoiler_ratio: float):
    """Generate and insert mock comments, then run AI detection."""
    init_db()
    db = SessionLocal()

    book = db.query(Book).filter(Book.id == book_id).first()
    if not book:
        print(f"Error: Book with id {book_id} not found.")
        db.close()
        return

    paragraphs = db.query(Paragraph).filter(Paragraph.book_id == book_id).order_by(Paragraph.para_index).all()
    if not paragraphs:
        print(f"Error: No paragraphs found for book id {book_id}.")
        db.close()
        return

    total_paras = len(paragraphs)
    num_spoilers = int(num_comments * spoiler_ratio)
    num_non_spoilers = num_comments - num_spoilers

    # Initialize services
    print("Loading embedding model...")
    emb_service = EmbeddingService()
    print("Initializing LLM service...")
    llm_service = LLMService()
    detector = SpoilerDetector(emb_service, llm_service)

    # Prepare paragraph dicts for semantic search
    para_dicts = [{"para_index": p.para_index, "content": p.content} for p in paragraphs]

    results = []
    print(f"\nGenerating {num_comments} comments ({num_spoilers} spoilers, {num_non_spoilers} non-spoilers)...")

    for i in range(num_comments):
        is_ground_truth_spoiler = i < num_spoilers
        comment_templates = SPOILER_COMMENTS if is_ground_truth_spoiler else NON_SPOILER_COMMENTS
        comment_text = random.choice(comment_templates)

        # For spoiler comments, pick a paragraph in the first half (so future content exists)
        # For non-spoiler comments, pick any paragraph
        if is_ground_truth_spoiler:
            para_index = random.randint(0, max(1, total_paras // 2))
        else:
            para_index = random.randint(0, total_paras - 1)

        paragraph = paragraphs[para_index]

        # Run AI detection
        try:
            ai_result = detector.detect(
                comment=comment_text,
                current_para_index=para_index,
                all_paragraphs=para_dicts,
            )
        except Exception as e:
            print(f"  Error detecting comment {i}: {e}")
            ai_result = {"is_spoiler": None, "confidence": 0.0, "reason": str(e), "status": "PENDING_REVIEW"}

        # Save comment with ground truth label in ai_reason for tracking
        ground_truth_label = "SPOILER" if is_ground_truth_spoiler else "NON_SPOILER"
        comment = Comment(
            paragraph_id=paragraph.id,
            book_id=book_id,
            content=comment_text,
            status=ai_result["status"],
            is_spoiler=ai_result["is_spoiler"],
            confidence=ai_result["confidence"],
            ai_reason=f"[GROUND_TRUTH:{ground_truth_label}] {ai_result['reason']}",
        )
        db.add(comment)
        db.commit()

        results.append({
            "ground_truth": is_ground_truth_spoiler,
            "ai_spoiler": ai_result["is_spoiler"],
            "confidence": ai_result["confidence"],
            "status": ai_result["status"],
        })

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{num_comments} comments...")

    db.close()

    # Generate accuracy report
    generate_report(results, spoiler_ratio)


def generate_report(results: list[dict], spoiler_ratio: float):
    """Generate and print accuracy report."""
    total = len(results)
    correct = 0
    true_spoilers = 0
    false_spoilers = 0
    true_non_spoilers = 0
    false_non_spoilers = 0

    for r in results:
        gt = r["ground_truth"]
        ai = r["ai_spoiler"]
        if gt and ai:
            true_spoilers += 1
            correct += 1
        elif gt and not ai:
            false_non_spoilers += 1
        elif not gt and ai:
            false_spoilers += 1
        else:
            true_non_spoilers += 1
            correct += 1

    accuracy = correct / total if total > 0 else 0
    spoiler_precision = true_spoilers / (true_spoilers + false_spoilers) if (true_spoilers + false_spoilers) > 0 else 0
    spoiler_recall = true_spoilers / (true_spoilers + false_non_spoilers) if (true_spoilers + false_non_spoilers) > 0 else 0

    print("\n" + "=" * 50)
    print("SPOILER SHIELD AI ACCURACY REPORT")
    print("=" * 50)
    print(f"Total comments:       {total}")
    print(f"Spoiler ratio:        {spoiler_ratio:.1%}")
    print(f"Overall accuracy:     {accuracy:.1%}")
    print(f"Spoiler precision:    {spoiler_precision:.1%}")
    print(f"Spoiler recall:       {spoiler_recall:.1%}")
    print(f"True positives:       {true_spoilers}")
    print(f"False positives:      {false_spoilers}")
    print(f"True negatives:       {true_non_spoilers}")
    print(f"False negatives:      {false_non_spoilers}")
    print("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate test comments and accuracy report")
    parser.add_argument("--book-id", type=int, required=True, help="Book ID to insert comments into")
    parser.add_argument("--num-comments", type=int, default=100, help="Number of comments to generate")
    parser.add_argument("--spoiler-ratio", type=float, default=0.3, help="Ratio of spoiler comments (0.0-1.0)")
    args = parser.parse_args()
    generate_comments(args.book_id, args.num_comments, args.spoiler_ratio)
```

- [ ] **Step 2: Verify script syntax**

Run: `python -c "import generate_test_comments; print('Script OK')"`
Expected: "Script OK"

- [ ] **Step 3: Commit**

```bash
git add generate_test_comments.py
git commit -m "feat: test comment generator and accuracy report script"
```

---

### Task 11: README Documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create README.md**

```markdown
# SpoilerShield MVP

AI-powered anti-spoiler reader. Upload ebooks, read them, comment on paragraphs — AI automatically detects and hides spoiler comments.

## Setup

1. Clone the repo and enter the directory
2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   venv\Scripts\activate     # Windows
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your OpenAI API key:
   ```bash
   cp .env.example .env
   ```
5. Run the application:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

## Usage

1. Visit `http://localhost:8000` — upload a PDF, EPUB, or TXT file
2. Click "Read" to enter the reading interface
3. Click any paragraph to open the comment sidebar
4. Post a comment — AI will automatically detect spoilers
5. Visit `http://localhost:8000/admin` to review low-confidence comments

## Test Script

Generate mock comments and view AI accuracy report:

```bash
python generate_test_comments.py --book-id 1 --num-comments 100 --spoiler-ratio 0.3
```

**Arguments:**
- `--book-id`: ID of the book (shown after upload)
- `--num-comments`: Number of comments to generate (default: 100)
- `--spoiler-ratio`: Ratio of spoiler vs non-spoiler comments (default: 0.3)

**Report output includes:**
- Overall accuracy
- Spoiler precision and recall
- True/false positive/negative counts

## Configuration

All settings are in `.env`:
- `OPENAI_API_KEY`: Your OpenAI API key
- `OPENAI_API_BASE`: OpenAI API base URL (default: https://api.openai.com/v1)
- `SPOILER_CONFIDENCE_THRESHOLD`: AI confidence threshold for auto-handling (default: 0.7)
- `LLM_MODEL`: LLM model name (default: gpt-4o)
- `EMBEDDING_MODEL`: Sentence-transformers model (default: all-MiniLM-L6-v2)
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: README with setup, usage, and test script documentation"
```

---

### Task 12: Integration Verification

**Files:** None (verification only)

- [ ] **Step 1: Start the application**

Run: `cd D:/Learn/workshop/CommentMask && uvicorn app.main:app --host 0.0.0.0 --port 8000 &`

- [ ] **Step 2: Verify ping endpoint**

Run: `curl http://localhost:8000/ping`
Expected: `{"status":"ok"}`

- [ ] **Step 3: Verify home page loads**

Run: `curl http://localhost:8000/`
Expected: HTML response with upload form

- [ ] **Step 4: Verify admin page loads**

Run: `curl http://localhost:8000/admin`
Expected: HTML response with admin panel

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Stop the server and final commit**

Kill the uvicorn process. If any issues were found during integration, fix them and commit.

```bash
git add -A
git commit -m "feat: SpoilerShield MVP complete — integration verified"
```

---

## Self-Review Checklist

1. **Spec coverage**: Each requirement in request_v1.1.md maps to a task:
   - File support (PDF/EPUB/TXT) → Task 3
   - Reading & commenting interface → Tasks 7, 8
   - AI spoiler detection pipeline → Tasks 4, 5
   - Comment display (blur/overlay/toggle) → Task 7 (templates)
   - Admin panel → Task 9
   - Test script & accuracy report → Task 10
   - Configuration (.env threshold) → Task 1

2. **Placeholder scan**: No TBD, TODO, or "implement later" found. All code steps contain complete implementation.

3. **Type consistency**: All model field names (`is_spoiler`, `confidence`, `ai_reason`, `status`, `para_index`, `book_id`, `paragraph_id`) are consistent across models, routers, services, and templates.