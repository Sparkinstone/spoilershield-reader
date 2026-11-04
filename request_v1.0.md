# Task: Build "SpoilerShield MVP" - AI-Powered Anti-Spoiler Reader

## Role & Project Context
You are a Senior Full-Stack Developer. Build a web-based PDF reader with an intelligent spoiler detection system.
- **Core Principle**: Use **RAG + Paragraph Indexing** to detect spoilers. If a comment relates to a paragraph index greater than the user's current position, it's a potential spoiler.
- **Tech Stack**: FastAPI (Python), HTMX (for dynamic UI), Tailwind CSS (styling), SQLite (database), and PyMuPDF (PDF parsing).
- **LLM**: GPT-4o (Read `OPENAI_API_KEY` and `OPENAI_API_BASE` from the existing `.env` file).

## Core Functionality & Logic

### 1. PDF Processing & RAG
- Parse uploaded PDFs into natural paragraphs.
- Store each paragraph in SQLite with metadata: `para_index`, `page_num`, `content`.
- Implement a simple vector search (using `sentence-transformers` or OpenAI embeddings) to retrieve relevant paragraphs for any given comment.

### 2. The Spoiler Detection Pipeline
When a user submits a comment on `para_index = X`:
1. **Semantic Retrieval**: Find the Top-3 most relevant paragraphs in the book.
2. **Positional Heuristic**: If any retrieved paragraph has an `index > X`, flag as `SPOILER_SUSPECT`.
3. **LLM Validation**: Send the comment, the current paragraph (X), and the retrieved "future" paragraphs to GPT-4o.
4. **JSON Response**: GPT-4o must return:
   ```json
   {
     "is_spoiler": boolean,
     "confidence": float, (0.0 to 1.0)
     "reason": "short explanation"
   }
   ```

### 3. Human-in-the-Loop Logic
- **THRESHOLD = 0.7** (Configurable).
- If `confidence >= THRESHOLD`: Automatically set status to `PUBLIC` or `HIDDEN` based on `is_spoiler`.
- If `confidence < THRESHOLD`: Set status to `PENDING_REVIEW`.

## UI/UX Requirements (HTMX Based)

### User Mode (Path: `/`)
- **Reader**: Display paragraphs sequentially. Click a paragraph to open a comment side-panel.
- **Comment Feed**: 
    - Normal comments: Visible.
    - Spoiler comments: Use `blur-sm` filter with a "Click to Reveal" overlay.
    - Pending comments: Show "Under AI moderation" for the author only.
- **Global Toggle**: A navbar switch to "Hide All Spoilers".

### Admin Mode (Path: `/admin`)
- A dashboard listing all `PENDING_REVIEW` comments.
- Show the comment text, the AI's `reason`, and `confidence` score.
- Actions: [Approve as Clean] [Mark as Spoiler] [Delete].

## Implementation Strategy
1. **Database Schema**: `paragraphs` table and `comments` table (fields: `id`, `para_index`, `content`, `status`, `is_spoiler`, `confidence`, `reason`).
2. **Modular Structure**:
    - `main.py`: FastAPI routes.
    - `database.py`: SQLAlchemy/SQLModel setup.
    - `pdf_engine.py`: PDF parsing and indexing.
    - `ai_service.py`: RAG logic and GPT-4o integration.
    - `templates/`: Jinja2 templates using HTMX.
3. **Environment**: Strictly use `python-dotenv` to load keys. Do not hardcode secrets.

**Action**: Start by generating the project structure, then implement the PDF parsing and Database models.